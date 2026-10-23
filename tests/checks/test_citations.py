"""Gate 13 for the documenter: each citation of each claim points at something that exists."""

import asyncio
from pathlib import Path

from forja.checks.citations import CitationCheck
from forja.core.artifacts.llm_output import (
    Citation,
    Claim,
    EvidenceCitation,
    FactCitation,
    FileCitation,
)
from forja.core.gates import Approved, GateInput, GateResult, Rejected

EVIDENCE = frozenset({"max_ccn", "build"})


def claim(*citations: Citation) -> Claim:
    return Claim(statement="something is true", citations=citations)


def file_at(path: str, start: int = 1, end: int = 1) -> FileCitation:
    return FileCitation(kind="file", path=path, line_start=start, line_end=end)


def judge(tmp_path: Path, *claims: Claim, facts: frozenset[str] = frozenset()) -> GateResult:
    (tmp_path / "src").mkdir(exist_ok=True)
    (tmp_path / "src" / "a.py").write_text("one\ntwo\nthree\n", encoding="utf-8")
    check = CitationCheck(tmp_path, claims, EVIDENCE, facts)
    return asyncio.run(check.evaluate(GateInput(tmp_path, "c" * 40, "t1", "t1-d", "t1-da1")))


def said(result: GateResult) -> list[str]:
    assert isinstance(result, Rejected)
    return [f.message for f in result.findings]


def test_claims_that_cite_existing_things_are_approved(tmp_path: Path) -> None:
    cited = claim(
        file_at("src/a.py", 1, 3),
        EvidenceCitation(kind="evidence", evidence_id="max_ccn"),
        FactCitation(kind="fact", fact_id="f1"),
    )
    assert isinstance(judge(tmp_path, cited, facts=frozenset({"f1"})), Approved)


def test_no_claims_is_nothing_to_check(tmp_path: Path) -> None:
    assert isinstance(judge(tmp_path), Approved)


def test_a_file_that_is_not_there_is_named(tmp_path: Path) -> None:
    assert said(judge(tmp_path, claim(file_at("src/none.py")))) == [
        "claim 1: src/none.py is not a file of the repository"
    ]


def test_lines_past_the_end_of_the_file_are_named_with_the_size(tmp_path: Path) -> None:
    assert said(judge(tmp_path, claim(file_at("src/a.py", 2, 4)))) == [
        "claim 1: src/a.py:2-4 is past the end of the file (3 lines)"
    ]


def test_a_directory_and_a_path_through_a_link_out_of_the_tree_are_not_files(
    tmp_path: Path,
) -> None:
    assert said(judge(tmp_path, claim(file_at("src")))) == [
        "claim 1: src is not a file of the repository"
    ]


def test_a_file_that_is_not_text_cannot_be_cited(tmp_path: Path) -> None:
    (tmp_path / "bin.dat").write_bytes(b"\xff\xfe\x00\x80")
    assert said(judge(tmp_path, claim(file_at("bin.dat")))) == [
        "claim 1: bin.dat cannot be read as text"
    ]


def test_evidence_that_nobody_measured_is_named(tmp_path: Path) -> None:
    result = judge(tmp_path, claim(EvidenceCitation(kind="evidence", evidence_id="speed")))
    assert said(result) == ["claim 1: no measurement or gate called 'speed'"]


def test_a_fact_nobody_recorded_is_named(tmp_path: Path) -> None:
    result = judge(tmp_path, claim(FactCitation(kind="fact", fact_id="f9")))
    assert said(result) == ["claim 1: no recorded fact 'f9'"]


def test_every_bad_citation_of_every_claim_is_reported_with_the_number_of_its_claim(
    tmp_path: Path,
) -> None:
    ok = claim(file_at("src/a.py"))
    bad = claim(file_at("src/none.py"), EvidenceCitation(kind="evidence", evidence_id="x"))
    assert said(judge(tmp_path, ok, bad)) == [
        "claim 2: src/none.py is not a file of the repository",
        "claim 2: no measurement or gate called 'x'",
    ]
