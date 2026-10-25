"""What the archaeologist found, sorted by what it rests on, and how it reaches the documenter.

The archaeologist declares claims, each with citations, and the premises it had to guess. The
Forja sorts: a claim that cites a fact a person recorded is *confirmed*, any other is *proven*
(its file and lines, or its measurement, were checked to exist by the gate); a premise is neither.
The documenter writes the three apart, so a reader knows which parts of the text are known.
"""

from collections.abc import Sequence

from forja.core.artifacts.llm_output import (
    Citation,
    Claim,
    EvidenceCitation,
    FactCitation,
    FileCitation,
    LlmOutput,
)
from forja.core.artifacts.models import Assumption
from forja.core.artifacts.schemas import Basis, FindingsBody, LabeledClaim
from forja.orchestrator.ports import RunContext


def findings_artifact_id(task_id: str) -> str:
    return f"findings-{task_id}"


def basis_of(claim: Claim) -> Basis:
    return (
        Basis.CONFIRMED
        if any(isinstance(c, FactCitation) for c in claim.citations)
        else Basis.PROVEN
    )


def findings_of(output: LlmOutput) -> FindingsBody:
    """The findings the archaeologist's answer makes, each claim with the basis the Forja gave."""
    return FindingsBody(
        claims=tuple(
            LabeledClaim(statement=c.statement, citations=c.citations, basis=basis_of(c))
            for c in output.claims
        )
    )


def _cited(citation: Citation) -> str:
    if isinstance(citation, FileCitation):
        return f"{citation.path}:{citation.line_start}-{citation.line_end}"
    if isinstance(citation, EvidenceCitation):
        return f"measurement {citation.evidence_id}"
    assert isinstance(citation, FactCitation)
    return f"fact {citation.fact_id}"


def _claim_lines(body: FindingsBody, basis: Basis) -> list[str]:
    return [
        f"- {c.statement} ({'; '.join(_cited(x) for x in c.citations)})"
        for c in body.claims
        if c.basis is basis
    ]


def render_findings(body: FindingsBody, premises: Sequence[Assumption]) -> str:
    """The findings in three lists, for the package of the documenter."""
    sections = [
        (
            "Proven (the cited files, lines and measurements exist)",
            _claim_lines(body, Basis.PROVEN),
        ),
        ("Confirmed (a person recorded the fact)", _claim_lines(body, Basis.CONFIRMED)),
        (
            "Premises (nobody verified them)",
            [
                f"- {a.statement} (why: {a.reason}; missing evidence: {a.missing_evidence})"
                for a in premises
            ],
        ),
    ]
    return "\n\n".join(
        f"### {title}\n\n" + ("\n".join(lines) or "None.") for title, lines in sections
    )


def findings_report(ctx: RunContext, task_id: str) -> str:
    """What the archaeologist of the task found, as it is told to the documenter."""
    stored = ctx.store.get(findings_artifact_id(task_id))
    body = stored.body
    assert isinstance(body, FindingsBody)
    return render_findings(body, stored.header.assumptions)
