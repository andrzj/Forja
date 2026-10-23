"""Gate 6: the end-to-end tests pass and none of them tried to reach the network.

The command is the repository's own (``[adapters.<language>.commands] e2e``); a language without
one is left out, and with none at all the gate does not run. Each run gets its own trap on
loopback as its proxy, so a destination in the trap rejects the attempt even when every test passed.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from forja.checks.base import Undecided, decided, measure_plan, rejected
from forja.checks.build_and_tests import FAILED
from forja.checks.e2e_plan import e2e_plan
from forja.checks.network_trap import NetworkTrap
from forja.checks.tooling import Tools
from forja.core.adapters import LanguageAdapter, NotSupported, Operation, OperationRequest
from forja.core.gates import (
    Approved,
    Finding,
    GateInput,
    GateResult,
    Inconclusive,
    InconclusiveReason,
    NotApplicable,
)

NO_COMMAND = "e2e_command"


@dataclass(frozen=True)
class E2ERun:
    """What the end-to-end runs of every language showed."""

    outcomes: dict[str, str]  # by test id
    destinations: tuple[str, ...]  # where a client tried to go, first attempt order


async def run_e2e(
    tools: Tools,
    adapters: Sequence[LanguageAdapter],
    worktree: Path,
    declared: Mapping[str, tuple[str, ...]],
    host_env: Mapping[str, str],
) -> E2ERun | None:
    """Run each language's declared E2E command; ``None`` when no language declares one.

    Raises ``Undecided`` when a run could not be made and nothing else was seen to fail first.
    """
    outcomes: dict[str, str] = {}
    destinations: dict[str, None] = {}
    undecided: Undecided | None = None
    ran = False
    for adapter in adapters:
        argv = declared.get(adapter.language)
        if argv is None:
            continue
        try:
            async with NetworkTrap() as trap:
                plan = e2e_plan(adapter, OperationRequest(root=worktree), argv, trap.url, host_env)
                if isinstance(plan, NotSupported):
                    continue
                ran = True
                try:
                    parsed = await measure_plan(tools, adapter, Operation.TEST, "e2e", plan)
                finally:  # a run that did not finish may still have tried the network
                    destinations.update(dict.fromkeys(trap.destinations))
        except OSError as problem:  # the trap did not open
            undecided = undecided or Undecided(
                Inconclusive(reason=InconclusiveReason.TOOL_FAILED, detail=f"e2e: {problem}")
            )
            continue
        except Undecided as stop:
            undecided = undecided or stop
            continue
        outcomes |= {
            d.target.id: str(d.value) for d in parsed.drafts if d.measurement == "test.outcome"
        }
    wrong = bool(destinations) or any(outcome in FAILED for outcome in outcomes.values())
    if undecided is not None and not wrong:  # a rejection wins over a run that could not be made
        raise undecided
    return E2ERun(outcomes, tuple(destinations)) if ran else None


@dataclass(frozen=True)
class E2ECheck:
    tools: Tools
    adapters: Sequence[LanguageAdapter]
    worktree: Path
    declared: Mapping[str, tuple[str, ...]]
    host_env: Mapping[str, str]
    quarantine: frozenset[str] = frozenset()  # end-to-end tests the base showed to be unstable
    passing: frozenset[str] = frozenset()  # end-to-end tests that passed on the base, both times
    id: str = "e2e"
    gate: int = 6
    requires: frozenset[str] = frozenset()

    async def evaluate(self, data: GateInput) -> GateResult:
        return await decided(self._judge())

    async def _judge(self) -> GateResult:
        run = await run_e2e(self.tools, self.adapters, self.worktree, self.declared, self.host_env)
        if run is None:
            return NotApplicable(missing_capability=NO_COMMAND)
        findings = [
            Finding(message=f"e2e test {outcome}", target=test)
            for test, outcome in sorted(run.outcomes.items())
            if outcome in FAILED and test not in self.quarantine
        ]
        findings += [
            Finding(
                message="an e2e test that passed on the base is missing or did not pass",
                target=test,
            )
            for test in sorted(self.passing - self.quarantine)
            if run.outcomes.get(test) != "passed" and test not in {f.target for f in findings}
        ]
        findings += [
            Finding(message="tried to reach the network", target=destination)
            for destination in run.destinations
        ]
        return rejected(findings) if findings else Approved()
