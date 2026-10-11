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
    base_tests: int = 0  # how many tests the base had; losing them all is a failure
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
        if any(d.measurement == "test.collected" for d in parsed.drafts):
            if self.base_tests == 0:
                return Approved()
            return rejected([Finding(message="no test was collected", target="tests")])
        findings = [
            Finding(message=f"test {draft.value}", target=draft.target.id)
            for draft in parsed.drafts
            if draft.measurement == "test.outcome"
            and draft.value in FAILED
            and draft.target.id not in self.quarantine
        ]
        return rejected(findings) if findings else Approved()
