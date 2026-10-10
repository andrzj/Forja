from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from forja.core.events.models import Ref, RefKind
from forja.core.gates import (
    CheckSettings,
    EvidenceItem,
    Finding,
    GateInput,
    GateResult,
    Inconclusive,
    InconclusivePolicy,
    InconclusiveReason,
    Mode,
    Rejected,
)
from tests.core.evidence.test_models import evidence

REJECTED = Rejected(findings=(Finding(message="too complex", target="src/a.py::f"),))
INCONCLUSIVE = Inconclusive(reason=InconclusiveReason.TOOL_FAILED, detail="the tool crashed")

BLOCKING = CheckSettings(Mode.BLOCKING, InconclusivePolicy.BLOCK)
BLOCKING_PREMISE = CheckSettings(Mode.BLOCKING, InconclusivePolicy.PREMISE)
OBSERVATION = CheckSettings(Mode.OBSERVATION)


@dataclass
class FakeCheck:
    id: str
    gate: int
    result: GateResult
    requires: frozenset[str] = frozenset()
    calls: list[GateInput] = field(default_factory=list)

    async def evaluate(self, data: GateInput) -> GateResult:
        self.calls.append(data)
        return self.result


class CrashingCheck:
    id = "crash"
    gate = 1
    requires: frozenset[str] = frozenset()

    async def evaluate(self, data: GateInput) -> GateResult:
        raise RuntimeError("bug in the check")


def evidence_ref(evidence_id: str = "ev1") -> Ref:
    return Ref(kind=RefKind.EVIDENCE, id=evidence_id, hash="a" * 64)


def make_input(tmp_path: Path, **changes: Any) -> GateInput:
    fields: dict[str, Any] = {
        "worktree": tmp_path,
        "commit": "d" * 40,
        "task_id": "t1",
        "stage_id": "s1",
        "attempt_id": "a1",
    }
    fields.update(changes)
    return GateInput(**fields)


def evidence_item(evidence_id: str = "ev1", **changes: Any) -> EvidenceItem:
    return EvidenceItem(evidence_ref(evidence_id), evidence(id=evidence_id, **changes))
