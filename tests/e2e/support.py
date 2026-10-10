"""What a new process does after a death, and the check that the run ended where it should."""

import asyncio
import os
from typing import Any

from forja.core.events import EventLog
from forja.core.idempotency import Decision
from forja.core.resume import ResumePlan, resume
from tests.e2e.driver import drive, reconciler
from tests.e2e.world import World, expected_after_discarding_one_attempt, fingerprint

# Lines the uninterrupted run writes; a test fails if the script grows past what is cut.
TOTAL_LINES = 60


class Counting:
    def __init__(self) -> None:
        self.count = 0

    def __call__(self, fd: int, data: bytes) -> int:
        self.count += 1
        return os.write(fd, data)


def run_until_it_ends(world: World, **log_options: Any) -> None:
    with world.open_log(**log_options) as log:
        asyncio.run(drive(world, log))


def restart(world: World, **log_options: Any) -> ResumePlan:
    """What a new process does: open the log, settle what was left open, carry on."""
    with world.open_log(**log_options) as log:
        plan = asyncio.run(resume(log, reconciler(world)))
        asyncio.run(drive(world, log))
    return plan


def label(event: Any) -> str:
    operation = getattr(event, "operation", None) or ""
    to_state = getattr(event, "to_state", None) or ""
    return f"{operation}{to_state}"


def open_operations(world: World) -> set[str]:
    """The operations the log shows as unfinished, read the way a new process would."""
    probe = world.root / "probe"
    probe.mkdir()
    copy = probe / "events.jsonl"
    copy.write_bytes(world.events.read_bytes())
    with EventLog.open(copy, "run1") as log:
        return {op.operation for op in log.state.open_operations.values()}


def assert_same_end(
    world: World, reference: dict[str, Any], plan: ResumePlan, open_at_crash: set[str]
) -> None:
    discards = [a for a in plan.actions if a.reconciliation.decision is Decision.DISCARD_ATTEMPT]
    after = fingerprint(world)
    if "call_agent_cli" in open_at_crash:
        assert [a.operation.operation for a in discards] == ["call_agent_cli"]
        assert after == expected_after_discarding_one_attempt(reference)
    else:
        assert discards == []
        assert after == reference
