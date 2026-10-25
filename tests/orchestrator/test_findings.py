"""What the archaeologist found, sorted by what it rests on and told to the documenter."""

import pytest
from pydantic import ValidationError

from forja.core.artifacts.llm_output import (
    Claim,
    EvidenceCitation,
    FactCitation,
    FileCitation,
    LlmOutput,
)
from forja.core.artifacts.models import Assumption
from forja.core.artifacts.schemas import Basis, FindingsBody, LabeledClaim
from forja.orchestrator.findings import basis_of, findings_of, render_findings

FILE = FileCitation(kind="file", path="src/a.py", line_start=3, line_end=9)
EVIDENCE = EvidenceCitation(kind="evidence", evidence_id="max_ccn")
FACT = FactCitation(kind="fact", fact_id="f1")


def claim(statement: str, *citations: FileCitation | EvidenceCitation | FactCitation) -> Claim:
    return Claim(statement=statement, citations=citations)


def test_a_claim_on_files_and_measurements_is_proven() -> None:
    assert basis_of(claim("a", FILE, EVIDENCE)) is Basis.PROVEN


def test_a_claim_that_cites_a_recorded_fact_is_confirmed_even_beside_a_file() -> None:
    assert basis_of(claim("a", FACT)) is Basis.CONFIRMED
    assert basis_of(claim("a", FILE, FACT)) is Basis.CONFIRMED


def test_the_findings_keep_the_order_and_the_citations_of_the_answer() -> None:
    answer = LlmOutput(claims=(claim("first", FILE), claim("second", FACT)))

    body = findings_of(answer)

    assert [(c.statement, c.basis) for c in body.claims] == [
        ("first", Basis.PROVEN),
        ("second", Basis.CONFIRMED),
    ]
    assert body.claims[0].citations == (FILE,)


def test_a_labeled_claim_cannot_say_a_basis_its_citations_do_not_hold() -> None:
    with pytest.raises(ValidationError, match="confirmed exactly when"):
        LabeledClaim(statement="a", citations=(FILE,), basis=Basis.CONFIRMED)
    with pytest.raises(ValidationError, match="confirmed exactly when"):
        LabeledClaim(statement="a", citations=(FACT,), basis=Basis.PROVEN)


def test_the_report_has_three_lists_and_says_where_each_claim_rests() -> None:
    body = findings_of(LlmOutput(claims=(claim("sums", FILE), claim("pages hold 10", FACT))))
    guess = Assumption(statement="pages start at 1", reason="no test", missing_evidence="a test")

    text = render_findings(body, (guess,))

    proven, confirmed, premises = text.split("### ")[1:]
    assert proven.startswith("Proven")
    assert "- sums (src/a.py:3-9)" in proven
    assert confirmed.startswith("Confirmed")
    assert "- pages hold 10 (fact f1)" in confirmed
    assert premises.startswith("Premises")
    assert "- pages start at 1 (why: no test; missing evidence: a test)" in premises


def test_a_kind_with_nothing_in_it_says_so() -> None:
    text = render_findings(FindingsBody(), ())

    assert text.count("None.") == 3


def test_a_measurement_is_named_in_the_report() -> None:
    body = findings_of(LlmOutput(claims=(claim("it is simple", EVIDENCE),)))

    assert "- it is simple (measurement max_ccn)" in render_findings(body, ())
