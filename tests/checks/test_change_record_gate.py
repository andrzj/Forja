"""Gate 14: the record of the task is there, whole, and says what the task's diff says."""

import asyncio
from pathlib import Path

from forja.checks.change_record import (
    REASONS,
    RecordFacts,
    SymbolChange,
    file_changes,
    record_path,
    render_changed,
    render_record,
)
from forja.checks.change_record_gate import ChangeRecordCheck
from forja.checks.changes import Change, ChangeKind, Changes
from forja.core.artifacts.llm_output import Claim, DeclaredChange, FileCitation
from forja.core.gates import Approved, GateInput, GateResult, Rejected

FILES = file_changes(Changes((Change(ChangeKind.MODIFIED, "src/a.py"),), 0, ()))
SYMBOLS = (SymbolChange("src/a.py", "f", "function", DeclaredChange.CREATED, True),)
CLAIM = Claim(
    statement="f was added",
    citations=(FileCitation(kind="file", path="src/a.py", line_start=1, line_end=2),),
)
EXPECTED = render_changed(FILES, SYMBOLS, ())


def facts(**extra: object) -> RecordFacts:
    base: dict[str, object] = {
        "task_id": "t1",
        "intent": "add f",
        "files": FILES,
        "symbols": SYMBOLS,
        "metrics_before": {},
        "metrics_after": {},
        "gates_passed": (),
        "toolchains": (),
        "executors": (),
        "revert_commit": "a" * 40,
    }
    return RecordFacts(**(base | extra))  # type: ignore[arg-type]


def judge(tmp_path: Path, text: str | None, expected: str = EXPECTED) -> GateResult:
    if text is not None:
        target = tmp_path / record_path("t1")
        target.parent.mkdir(parents=True)
        target.write_text(text, encoding="utf-8")
    check = ChangeRecordCheck(tmp_path, "t1", expected)
    return asyncio.run(check.evaluate(GateInput(tmp_path, "c" * 40, "t1", "t1-d", "t1-da1")))


def messages(result: GateResult) -> list[str]:
    assert isinstance(result, Rejected)
    return [f.message for f in result.findings]


def test_a_complete_record_that_matches_the_diff_is_approved(tmp_path: Path) -> None:
    assert isinstance(judge(tmp_path, render_record(facts(), [CLAIM])), Approved)


def test_a_record_that_is_not_there_is_rejected(tmp_path: Path) -> None:
    assert messages(judge(tmp_path, None)) == ["the change record is missing"]


def test_a_record_without_a_section_is_rejected_naming_it(tmp_path: Path) -> None:
    text = render_record(facts(), [CLAIM]).replace("## Para reverter", "## Outra coisa")
    assert messages(judge(tmp_path, text)) == [
        "the change record lacks the section '## Para reverter'"
    ]


def test_a_record_whose_files_or_symbols_differ_from_the_diff_is_rejected(tmp_path: Path) -> None:
    other = render_changed(
        FILES, (SymbolChange("src/a.py", "g", "function", DeclaredChange.CREATED, True),), ()
    )
    assert messages(judge(tmp_path, render_record(facts(), [CLAIM]), other)) == [
        "the files and symbols in the change record differ from the task's changes"
    ]


def test_a_record_with_no_cited_reason_is_rejected(tmp_path: Path) -> None:
    assert messages(judge(tmp_path, render_record(facts(), []))) == [
        "the change record has no reason or impact with a citation"
    ]


def test_a_record_cut_off_at_the_reasons_is_rejected(tmp_path: Path) -> None:
    text = render_record(facts(), [CLAIM]).split(REASONS)[0] + REASONS + "\n"
    assert messages(judge(tmp_path, text)) == [
        "the change record has no reason or impact with a citation"
    ]
