"""One check per language, answering as one: the verdict of a project with more than one."""

from collections.abc import Sequence
from dataclasses import dataclass

from forja.checks.base import rejected
from forja.core.gates import (
    Approved,
    Check,
    GateInput,
    GateResult,
    Inconclusive,
    NotApplicable,
    Rejected,
)


@dataclass(frozen=True)
class Part:
    """A check and the capabilities of the adapter it was made for."""

    check: Check
    capabilities: frozenset[str]


@dataclass(frozen=True)
class EachLanguage:
    """Runs a check made for each language and merges the answers.

    A part whose adapter lacks a capability the check needs is not applicable. A rejection wins,
    then an inconclusive part (a language nobody could measure is not a pass), then an approval.
    """

    parts: Sequence[Part]
    id: str
    gate: int
    requires: frozenset[str] = frozenset()

    async def evaluate(self, data: GateInput) -> GateResult:
        results: list[GateResult] = []
        for part in self.parts:
            absent = sorted(part.check.requires - part.capabilities)
            if absent:
                results.append(NotApplicable(missing_capability=absent[0]))
            else:
                results.append(await part.check.evaluate(data))
        return merge(results)


def merge(results: Sequence[GateResult]) -> GateResult:
    findings = [f for r in results if isinstance(r, Rejected) for f in r.findings]
    if findings:
        return rejected(findings)
    for result in results:
        if isinstance(result, Inconclusive):
            return result
    for result in results:
        if isinstance(result, Approved):
            return result
    return results[0]
