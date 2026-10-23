"""Gate 14: the change record of the task is in the documenter's work and is complete.

The Forja writes the record itself before the gate runs, so the gate does not trust it blindly: it
looks for every section, renders the files and symbols again from the task's diff and looks for
them in the text, and requires a reason or an impact the documenter cited.
"""

from dataclasses import dataclass
from pathlib import Path

from forja.checks.base import decided, rejected
from forja.checks.change_record import NONE, REASONS, SECTIONS, record_path
from forja.core.gates import Approved, Finding, GateInput, GateResult


@dataclass(frozen=True)
class ChangeRecordCheck:
    worktree: Path
    task_id: str
    expected: str  # the files and symbols section as the task's diff renders them now
    id: str = "change_record"
    gate: int = 14
    requires: frozenset[str] = frozenset()

    async def evaluate(self, data: GateInput) -> GateResult:
        return await decided(self._judge())

    async def _judge(self) -> GateResult:
        path = record_path(self.task_id)
        try:
            text = (self.worktree / path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return rejected([Finding(message="the change record is missing", target=path)])
        findings = [
            Finding(message=f"the change record lacks the section {heading!r}", target=path)
            for heading in SECTIONS
            if f"\n{heading}\n" not in text
        ]
        if self.expected not in text:
            message = "the files and symbols in the change record differ from the task's changes"
            findings.append(Finding(message=message, target=path))
        if REASONS in text:
            reasons = text.split(REASONS, 1)[1].strip()
            if not reasons or reasons == NONE:
                message = "the change record has no reason or impact with a citation"
                findings.append(Finding(message=message, target=path))
        return rejected(findings) if findings else Approved()
