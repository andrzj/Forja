"""Gate 12: markers of text written on autopilot, in documents and in comments, never in strings."""

import asyncio
from pathlib import Path
from typing import Any

import pytest

from forja.checks.changes import Change, ChangeKind, Changes
from forja.checks.voice import VoiceCheck, comment_lines
from forja.checks.voice_markers import MARKERS
from forja.core.adapters import AdapterRegistry, FileClass
from forja.core.gates import Approved, GateInput, GateResult, Rejected
from forja.languages.python import PythonAdapter


def classify(path: str) -> FileClass:
    registry = AdapterRegistry()
    registry.register_language(PythonAdapter())
    return registry.classify(path)


def patch_adding(path: str, *lines: str, start: int = 1) -> tuple[str, ...]:
    head = (f"diff --git a/{path} b/{path}", "--- /dev/null", f"+++ b/{path}")
    return (*head, f"@@ -0,0 +{start},{len(lines)} @@", *(f"+{line}" for line in lines))


def judge(
    tmp_path: Path, path: str, text: str, *, values: dict[str, Any] | None = None
) -> GateResult:
    target = tmp_path / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    lines = text.splitlines()
    changes = Changes((Change(ChangeKind.ADDED, path),), len(lines), patch_adding(path, *lines))
    check = VoiceCheck(tmp_path, changes, classify)
    data = GateInput(tmp_path, "c" * 40, "t1", "t1-s", "t1-a1", values=values or {})
    return asyncio.run(check.evaluate(data))


def test_lines_added_to_no_file_are_never_read(tmp_path: Path) -> None:
    patch = ("+++ /dev/null", "@@ -0,0 +1 @@", "+# Sure! here it is")
    check = VoiceCheck(tmp_path, Changes((), 1, patch), classify)
    data = GateInput(tmp_path, "c" * 40, "t1", "t1-s", "t1-a1")
    assert isinstance(asyncio.run(check.evaluate(data)), Approved)


def said(result: GateResult) -> list[tuple[str, str]]:
    assert isinstance(result, Rejected)
    return [(f.target, f.message) for f in result.findings]


@pytest.mark.parametrize(
    ("line", "why"),
    [
        ("Sure! Here is the guide.", "an opening that greets instead of saying something"),
        ("Claro, segue o guia.", "an opening that greets instead of saying something"),
        ("As an AI I cannot say.", "the model talks about itself"),
        ("Let us delve into the parser.", "vocabulary that inflates and says nothing"),
        (
            "It is worth noting that x is 1.",
            "a sentence that announces that something matters instead of saying it",
        ),
        (
            "Vale ressaltar que x vale 1.",
            "a sentence that announces that something matters instead of saying it",
        ),
        ("I hope this helps.", "an offer of more help, to a reader who is a repository"),
        ("Done \U0001f680", "an emoji in text that is read as documentation"),
    ],
)
def test_a_marker_in_a_document_is_found_with_its_line_and_never_its_text(
    tmp_path: Path, line: str, why: str
) -> None:
    result = judge(tmp_path, "README.md", f"# Title\n\n{line}\n")
    assert said(result) == [("README.md", why)]
    assert isinstance(result, Rejected)
    assert result.findings[0].location is not None
    assert result.findings[0].location.line == 3


def test_a_plain_document_is_approved(tmp_path: Path) -> None:
    text = "# Title\n\nThe parser reads one token at a time and stops at the first error.\n"
    assert isinstance(judge(tmp_path, "docs/guide.md", text), Approved)


def test_a_marker_in_a_comment_is_found_and_the_same_words_in_a_string_are_not(
    tmp_path: Path,
) -> None:
    code = 'x = "Sure! it is worth noting that"\n# Certainly, this adds one.\ny = x\n'
    result = judge(tmp_path, "src/a.py", code)
    assert said(result) == [("src/a.py", "an opening that greets instead of saying something")]
    assert isinstance(result, Rejected)
    assert result.findings[0].location is not None
    assert result.findings[0].location.line == 2


def test_code_with_no_comment_is_never_prose(tmp_path: Path) -> None:
    assert isinstance(judge(tmp_path, "src/a.py", 'x = "Sure! I hope this helps"\n'), Approved)


def test_a_file_that_is_neither_a_document_nor_a_language_the_forja_reads_is_left_alone(
    tmp_path: Path,
) -> None:
    assert isinstance(judge(tmp_path, "data.json", '{"a": "Sure! I hope this helps"}\n'), Approved)


def test_a_source_file_that_does_not_parse_is_left_alone(tmp_path: Path) -> None:
    assert isinstance(judge(tmp_path, "src/a.py", "# Sure! ok\ndef (:\n"), Approved)


def test_more_em_dashes_than_the_limit_in_one_file_are_excess(tmp_path: Path) -> None:
    text = "a — b\nc — d\ne — f\ng — h\n"
    result = judge(tmp_path, "README.md", text)
    assert said(result) == [("README.md", "too many em dashes in the added text")]
    assert isinstance(result, Rejected)
    assert (result.findings[0].measured, result.findings[0].limit) == (4, 3)


def test_the_limit_of_dashes_is_the_policys_when_it_sets_one(tmp_path: Path) -> None:
    text = "a — b\nc — d\ne — f\ng — h\n"
    assert isinstance(
        judge(tmp_path, "README.md", text, values={"limits": {"max_dashes": 4}}), Approved
    )


def test_the_comment_lines_cover_a_block_comment_from_first_to_last_line() -> None:
    source = "x = 1\n# one\ny = 2\n"
    assert comment_lines("a.py", source) == frozenset({2})
    assert comment_lines("a.ts", "/* a\n b */\nlet x = 1;\n") == frozenset({1, 2})
    assert comment_lines("a.txt", "# not code") is None


def test_every_marker_says_why_it_is_on_the_list() -> None:
    assert all(marker.why for marker in MARKERS)
    assert len({marker.id for marker in MARKERS}) == len(MARKERS)
