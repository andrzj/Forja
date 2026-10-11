"""Gates 4 and 5: the project still builds, and its tests still pass."""

from dataclasses import dataclass
from pathlib import Path

from forja.checks.base import decided, measure, overrides_from, rejected
from forja.checks.tooling import Tools
from forja.core.adapters import LanguageAdapter, Operation, OperationRequest
from forja.core.gates import Approved, Finding, GateInput, GateResult

FAILED = ("failed", "error")


@dataclass(frozen=True)
class BuildCheck:
    tools: Tools
    adapter: LanguageAdapter
    worktree: Path
    id: str = "build"
    gate: int = 4
    requires: frozenset[str] = frozenset()

    async def evaluate(self, data: GateInput) -> GateResult:
        return await decided(self._judge(data))

    async def _judge(self, data: GateInput) -> GateResult:
        request = OperationRequest(root=self.worktree)
        overrides = overrides_from(self.adapter, data.values)
        parsed = await measure(
            self.tools, self.adapter, Operation.BUILD, "build", request, overrides
        )
        findings = [
            Finding(
                message="the file does not compile"
                if draft.measurement == "build.compile_error"
                else "the build failed",
                target=draft.target.id,
            )
            for draft in parsed.drafts
        ]
        return rejected(findings) if findings else Approved()


@dataclass(frozen=True)
class TestsCheck:
    """Every test passes, except the ones the base already showed to be unstable (quarantine)."""

    __test__ = False  # not a test class, whatever its name says to pytest

    tools: Tools
    adapter: LanguageAdapter
    worktree: Path
    quarantine: frozenset[str] = frozenset()
    passing: frozenset[str] = frozenset()  # tests that passed on the base, both times
    id: str = "tests"
    gate: int = 5
    requires: frozenset[str] = frozenset()

    async def evaluate(self, data: GateInput) -> GateResult:
        return await decided(self._judge(data))

    async def _judge(self, data: GateInput) -> GateResult:
        request = OperationRequest(root=self.worktree)
        overrides = overrides_from(self.adapter, data.values)
        parsed = await measure(
            self.tools, self.adapter, Operation.TEST, "tests", request, overrides
        )
        outcomes = {
            d.target.id: str(d.value) for d in parsed.drafts if d.measurement == "test.outcome"
        }
        findings = [
            Finding(message=f"test {outcome}", target=test)
            for test, outcome in sorted(outcomes.items())
            if outcome in FAILED and test not in self.quarantine
        ]
        # a test that vanished, was skipped or deleted is a failure nobody reported
        findings += [
            Finding(
                message="a test that passed on the base is missing or did not pass", target=test
            )
            for test in sorted(self.passing - self.quarantine)
            if outcomes.get(test) != "passed" and test not in {f.target for f in findings}
        ]
        return rejected(findings) if findings else Approved()
