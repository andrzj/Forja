"""Gate 6: the test and fixture files hold no personal data the attempt added (the ratchet).

The detectors are the redaction ones (CPF, CNPJ, e-mail, phone, card), each with its own validity
test, so reserved domains and numbers with a wrong check digit are left alone. A finding is counted
per file and kind, so moving a line, or renaming the file, does not make old data look new. The
value found is never copied into a finding: the next attempt is told the kind and the file.
"""

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from forja.checks.base import Undecided, decided, rejected
from forja.checks.changes import Changes
from forja.core.gates import (
    Approved,
    Finding,
    GateInput,
    GateResult,
    Inconclusive,
    InconclusiveReason,
)
from forja.core.redaction.pii import DETECTORS

Counts = Counter[str]  # by kind


def personal_data_in(text: str) -> Counts:
    """How many places of ``text`` hold personal data, by kind; each place counts once."""
    counts: Counts = Counter()
    for detector in DETECTORS:
        spans = sorted(
            match.span()
            for pattern in detector.patterns
            for match in pattern.finditer(text)
            if detector.valid(match.group())
        )
        places, end = 0, -1
        for start, stop in spans:
            if start >= end:  # one that overlaps the previous place is the same place
                places += 1
            end = max(end, stop)
        if places:
            counts[detector.kind.value] = places
    return counts


@dataclass(frozen=True)
class PersonalDataCheck:
    worktree: Path
    changes: Changes
    before: dict[str, str]  # the parent commit's text of the changed test files, by old path
    is_test: Callable[[str], bool]  # a test or a fixture, as the language adapters class it
    id: str = "test_data"
    gate: int = 6
    requires: frozenset[str] = frozenset()

    async def evaluate(self, data: GateInput) -> GateResult:
        return await decided(self._judge())

    async def _judge(self) -> GateResult:
        findings: list[Finding] = []
        unreadable: list[str] = []
        for change in self.changes.files:
            if not change.exists_now or not self.is_test(change.path):
                continue
            try:
                text = (self.worktree / change.path).read_bytes().decode("utf-8", errors="replace")
            except OSError:  # what is in it is unknown, so it is never taken for clean
                unreadable.append(change.path)
                continue
            was = personal_data_in(self.before.get(change.before or "", ""))
            for kind, count in sorted(personal_data_in(text).items()):
                if count > was[kind]:
                    message = f"{count - was[kind]} new {kind} value(s) in test data"
                    findings.append(
                        Finding(
                            message=message, target=change.path, measured=count, limit=was[kind]
                        )
                    )
        if findings:
            return rejected(findings)
        if unreadable:
            raise Undecided(
                Inconclusive(
                    reason=InconclusiveReason.TOOL_FAILED,
                    detail="test_data: cannot read " + ", ".join(unreadable[:3]),
                )
            )
        return Approved()
