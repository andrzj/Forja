"""Gate 13, for the specifier: every element of the input becomes a criterion, and no criterion is
without an origin.

An element the specifier leaves out is not rejected, because it says so with a reason, and that
reason is an assumption the summary shows. That a criterion says what its element says is for the
reviewer; this only ties the ids together.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from forja.checks.base import rejected
from forja.core.artifacts.elements import Element
from forja.core.artifacts.llm_output import Criterion, LeftOut
from forja.core.gates import Approved, Finding, GateInput, GateResult


@dataclass(frozen=True)
class TraceabilityCheck:
    elements: Sequence[Element]
    criteria: Sequence[Criterion]
    left_out: Sequence[LeftOut] = ()
    id: str = "traceability"
    gate: int = 13
    requires: frozenset[str] = frozenset()

    async def evaluate(self, data: GateInput) -> GateResult:
        known = {element.id for element in self.elements}
        findings = [
            *self._unknown_origins(known),
            *self._unknown_left_out(known),
            *self._without_criterion(),
        ]
        return rejected(findings) if findings else Approved()

    def _unknown_origins(self, known: set[str]) -> list[Finding]:
        findings = []
        for criterion in self.criteria:
            for origin in criterion.origin:
                if origin not in known:
                    message = (
                        f"criterion {criterion.id} comes from {origin}, which is not in the input"
                    )
                    findings.append(Finding(message=message, target=f"criterion {criterion.id}"))
        return findings

    def _unknown_left_out(self, known: set[str]) -> list[Finding]:
        return [
            Finding(
                message=f"{item.element} is left out but is not in the input", target=item.element
            )
            for item in self.left_out
            if item.element not in known
        ]

    def _without_criterion(self) -> list[Finding]:
        covered = {origin for criterion in self.criteria for origin in criterion.origin}
        covered |= {item.element for item in self.left_out}
        return [
            Finding(
                message=f"{element.id} has no criterion and is not left out: {element.text[:80]}",
                target=element.id,
            )
            for element in self.elements
            if element.id not in covered
        ]
