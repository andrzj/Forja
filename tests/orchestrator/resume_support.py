"""The scenario every resume test shares, and the facts that say two runs ended the same way."""

import copy
from typing import Any

from forja.core.events import EventLog
from forja.core.states import AttemptState, Level
from forja.orchestrator.outcome import Outcome
from tests.orchestrator.fakes import ContentMeasurer, ScriptedAgent
from tests.orchestrator.harness import RUN, World


def scenario(world: World, **options: Any) -> tuple[Outcome, EventLog]:
    """One task; the agent first writes work the gate rejects, then work it accepts."""
    options.setdefault("agent", ScriptedAgent(by_feedback=True))
    options.setdefault("measurer", ContentMeasurer())
    return world.run(**options)


def attempt_states(log: EventLog) -> list[AttemptState]:
    states = []
    for attempt in log.state.children_of(Level.ATTEMPT, "t1-s"):
        state = log.state.state_of(Level.ATTEMPT, attempt)
        assert isinstance(state, AttemptState)
        states.append(state)
    return states


def agent_was_running(world: World) -> bool:
    """Whether the log, as the dead process left it, shows an attempt in the middle of its call."""
    probe = world.root / "probe"
    probe.mkdir(exist_ok=True)
    copy_of_log = probe / "events.jsonl"
    copy_of_log.write_bytes((world.run_dir / "events.jsonl").read_bytes())
    with EventLog.open(copy_of_log, RUN) as log:
        return any(op.operation == "call_agent_cli" for op in log.state.open_operations.values())


def fingerprint(world: World, log: EventLog) -> dict[str, Any]:
    """The facts two runs must share to have ended in the same place.

    Ids and times are left out because they differ from run to run; commits are compared by tree.
    The summary is included whole: it is written from the log, so it must come out the same.
    """
    state = log.state
    run_branch = world.workspace.run_branch
    attempts: dict[str, int] = {}
    for current in attempt_states(log):
        attempts[current.value] = attempts.get(current.value, 0) + 1
    discards = [
        state.transition_payload(Level.ATTEMPT, a, AttemptState.DISCARDED) or {}
        for a in state.children_of(Level.ATTEMPT, "t1-s")
        if state.state_of(Level.ATTEMPT, a) is AttemptState.DISCARDED
    ]
    return {
        "execution": state.state_of(Level.EXECUTION, RUN).value,
        "task": state.state_of(Level.TASK, "t1").value,
        "stage": state.state_of(Level.STAGE, "t1-s").value,
        "attempts": attempts,
        "infra_failures": sum(1 for d in discards if d.get("infra_failure") is True),
        "open_operations": sorted(state.open_operations),
        "refs": sorted(world.repo.sh("for-each-ref", "--format=%(refname)").splitlines()),
        "run_tree": world.repo.sh("rev-parse", f"{run_branch}^{{tree}}"),
        "commits": world.repo.sh("rev-list", "--count", run_branch),
        "worktrees": len(world.repo.sh("worktree", "list").splitlines()),
        "summary": (world.run_dir / "resumo.md")
        .read_text(encoding="utf-8")
        .replace(str(world.run_dir), "<run>"),
        "blobs": sorted(p.name for p in (world.run_dir / "store" / "blobs").glob("*")),
    }


def with_one_more_discarded_attempt(reference: dict[str, Any]) -> dict[str, Any]:
    """The reference run plus the attempt whose agent call could not be trusted."""
    expected = copy.deepcopy(reference)
    expected["attempts"]["discarded"] = expected["attempts"].get("discarded", 0) + 1
    expected["infra_failures"] += 1
    return expected
