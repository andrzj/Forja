"""Gate 13, for the documenter: every claim cites something that exists.

A claim is a statement with at least one citation (the output contract refuses one with none).
Here each citation is checked against the world: the file is in the worktree and has the lines, the
evidence is a measurement or a gate the Forja has, and the fact is one a person recorded. What the
gate cannot tell is whether the cited lines say what the claim says; that is for the reviewer.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from forja.checks.base import decided, rejected
from forja.core.artifacts.llm_output import (
    Citation,
    Claim,
    EvidenceCitation,
    FactCitation,
    FileCitation,
)
from forja.core.gates import Approved, Finding, GateInput, GateResult


@dataclass(frozen=True)
class CitationCheck:
    worktree: Path
    claims: Sequence[Claim]
    evidence_ids: frozenset[str]  # the measurements and gates a claim may point at
    fact_ids: frozenset[str] = frozenset()  # facts a person recorded; none exist yet
    id: str = "citations"
    gate: int = 13
    requires: frozenset[str] = frozenset()

    async def evaluate(self, data: GateInput) -> GateResult:
        return await decided(self._judge())

    async def _judge(self) -> GateResult:
        findings = []
        for number, claim in enumerate(self.claims, start=1):
            for citation in claim.citations:
                problem = self._problem(citation)
                if problem:
                    findings.append(
                        Finding(message=f"claim {number}: {problem}", target=_target(citation))
                    )
        return rejected(findings) if findings else Approved()

    def _problem(self, citation: Citation) -> str:
        if isinstance(citation, FileCitation):
            return self._file_problem(citation)
        if isinstance(citation, EvidenceCitation):
            known = citation.evidence_id in self.evidence_ids
            return "" if known else f"no measurement or gate called {citation.evidence_id!r}"
        assert isinstance(citation, FactCitation)
        return "" if citation.fact_id in self.fact_ids else f"no recorded fact {citation.fact_id!r}"

    def _file_problem(self, citation: FileCitation) -> str:
        root = self.worktree.resolve()
        path = (self.worktree / citation.path).resolve()
        where = f"{citation.path}:{citation.line_start}-{citation.line_end}"
        if root not in path.parents or not path.is_file():
            return f"{citation.path} is not a file of the repository"
        try:
            lines = len(path.read_text(encoding="utf-8").splitlines())
        except (OSError, UnicodeDecodeError):
            return f"{citation.path} cannot be read as text"
        if citation.line_end > lines:
            return f"{where} is past the end of the file ({lines} lines)"
        return ""


def _target(citation: Citation) -> str:
    if isinstance(citation, FileCitation):
        return citation.path
    if isinstance(citation, EvidenceCitation):
        return citation.evidence_id
    return citation.fact_id
