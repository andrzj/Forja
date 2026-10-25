"""Gate 12, the Ousterhout rules: comments that repeat the code, interface with no comment."""

import asyncio
from pathlib import Path

import pytest

from forja.checks.changes import Change, ChangeKind, Changes
from forja.checks.comments import CommentsCheck, repeats, words
from forja.checks.symbols import symbols_in
from forja.core.adapters import AdapterRegistry, FileClass
from forja.core.gates import Approved, GateInput, GateResult, Rejected
from forja.languages.python import PythonAdapter

MODULE = '"""Module."""'
DOC = '    """Doc."""'
TOTAL_PRICE = ["def total_price(items):", DOC, "    return 0", ""]


def classify(path: str) -> FileClass:
    registry = AdapterRegistry()
    registry.register_language(PythonAdapter())
    return registry.classify(path)


def judge(
    tmp_path: Path, text: str, before: str | None = None, path: str = "src/a.py"
) -> GateResult:
    target = tmp_path / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    count = len(text.splitlines())
    if before is None:
        change, old = Change(ChangeKind.ADDED, path), {}
        patch = (f"+++ b/{path}", f"@@ -0,0 +1,{count} @@", *(f"+{x}" for x in text.splitlines()))
    else:
        change, old = Change(ChangeKind.MODIFIED, path), {path: before}
        patch = (f"+++ b/{path}", f"@@ -0,0 +1,{count} @@", *(f"+{x}" for x in text.splitlines()))
        patch = _only_new(path, text, before)
    check = CommentsCheck(tmp_path, Changes((change,), count, patch), old, classify)
    return asyncio.run(check.evaluate(GateInput(tmp_path, "c" * 40, "t1", "t1-s", "t1-a1")))


def _only_new(path: str, text: str, before: str) -> tuple[str, ...]:
    old = set(before.splitlines())
    rows = [(n, line) for n, line in enumerate(text.splitlines(), start=1) if line not in old]
    out = [f"+++ b/{path}"]
    for n, line in rows:
        out += [f"@@ -0,0 +{n},1 @@", f"+{line}"]
    return tuple(out)


def said(result: GateResult) -> list[tuple[str, int | None]]:
    assert isinstance(result, Rejected)
    return [(f.message, f.location.line if f.location else None) for f in result.findings]


def test_words_split_identifiers_and_drop_the_filler() -> None:
    assert words("get_total_price(items)") == {"get", "total", "price", "items"}
    assert words("Return the total of the Items") == {"return", "total", "items"}
    assert words("parseHTTPResponse") == {"parse", "http", "response"}


@pytest.mark.parametrize(
    ("comment", "code", "expected"),
    [
        ("# total price of the items", "def total_price(items):", True),
        ("# Increment the counter", "counter += 1", False),
        ("# counter counter", "counter += 1", False),
        ("# noqa", "import os", False),
        ("# retries because the server drops idle connections", "def retries(server):", False),
        ("// get the user name", "getUserName()", True),
        ("/* set the retry limit */", "setRetryLimit(3);", True),
        ("# alpha beta gamma delta", "alpha beta gamma", True),
    ],
)
def test_a_comment_repeats_the_code_when_nearly_all_its_words_are_the_codes(
    comment: str, code: str, expected: bool
) -> None:
    assert repeats(comment, code) is expected


def test_a_new_comment_that_repeats_the_line_below_it_is_found_at_its_line(tmp_path: Path) -> None:
    code = "\n".join([MODULE, "", "", "# total price of the items", *TOTAL_PRICE])
    assert said(judge(tmp_path, code)) == [("a comment repeats the code next to it", 4)]


def test_a_trailing_comment_is_read_against_its_own_line(tmp_path: Path) -> None:
    body = ["    total_price = sum(items)  # total price", "    return total_price"]
    code = "\n".join([MODULE, "", "", "def f(items):", DOC, *body, ""])
    assert said(judge(tmp_path, code)) == [("a comment repeats the code next to it", 6)]


def test_a_trailing_comment_is_not_read_against_the_line_below(tmp_path: Path) -> None:
    body = ["    total_price = sum(items)  # total price", "    return 0"]
    code = "\n".join([MODULE, "", "", "def f(items):", DOC, *body, ""])
    assert said(judge(tmp_path, code)) == [("a comment repeats the code next to it", 6)]


def test_a_comment_with_no_code_after_it_has_nothing_to_repeat(tmp_path: Path) -> None:
    code = "\n".join([MODULE, "", "", "x = 1", "", "# something unrelated here", ""])
    assert isinstance(judge(tmp_path, code), Approved)


def test_code_further_than_the_next_line_is_not_what_the_comment_is_about(tmp_path: Path) -> None:
    code = "\n".join([MODULE, "", "# total price of the items", "", "", *TOTAL_PRICE])
    assert isinstance(judge(tmp_path, code), Approved)


def test_a_comment_above_a_declaration_is_read_against_its_header_only(tmp_path: Path) -> None:
    body = ["# compute total price", "def run(items):", "    compute_total_price = items", ""]
    code = "\n".join([MODULE, "", "", *body])
    assert isinstance(judge(tmp_path, code), Approved)


def test_a_comment_that_is_the_only_line_added_is_still_judged(tmp_path: Path) -> None:
    old = "\n".join([MODULE, "", "", "def f(items):", DOC, "    total_price = sum(items)", ""])
    new = old.replace("sum(items)", "sum(items)  # total price")
    assert said(judge(tmp_path, new, before=old)) == [("a comment repeats the code next to it", 6)]


def test_a_comment_that_says_why_is_approved(tmp_path: Path) -> None:
    body = ["    # the server may send nothing at all", "    return sum(items)"]
    code = "\n".join([MODULE, "", "", "def f(items):", DOC, *body, ""])
    assert isinstance(judge(tmp_path, code), Approved)


def test_an_old_comment_is_never_blamed(tmp_path: Path) -> None:
    old = "\n".join([MODULE, "", "", "# total price of the items", *TOTAL_PRICE])
    new = old + "\n\ndef other():\n    '''Doc.'''\n"
    assert isinstance(judge(tmp_path, new, before=old), Approved)


def test_a_new_public_function_with_no_comment_is_found(tmp_path: Path) -> None:
    code = '"""M."""\n\n\ndef add(a, b):\n    return a + b\n'
    assert said(judge(tmp_path, code)) == [("the new public function add has no comment", 4)]


def test_a_docstring_or_a_comment_above_documents_a_symbol(tmp_path: Path) -> None:
    code = (
        '"""M."""\n\n\ndef add(a, b):\n    """Sum."""\n    return a + b\n\n\n'
        "# Product of two numbers, kept apart from add.\ndef mul(a, b):\n    return a * b\n"
    )
    assert isinstance(judge(tmp_path, code), Approved)


def test_a_private_symbol_and_a_symbol_that_was_already_there_are_left_alone(
    tmp_path: Path,
) -> None:
    old = '"""M."""\n\n\ndef add(a, b):\n    return a + b\n'
    new = old + "\n\ndef _hidden():\n    return 1\n"
    assert isinstance(judge(tmp_path, new, before=old), Approved)


def test_a_test_file_needs_no_comment_on_its_public_functions(tmp_path: Path) -> None:
    code = "def test_add():\n    assert 1 + 1 == 2\n"
    assert isinstance(judge(tmp_path, code, path="tests/test_a.py"), Approved)


@pytest.mark.parametrize(
    ("path", "source", "documented"),
    [
        ("a.py", "def f():\n    '''Doc.'''\n    return 1\n", True),
        ("a.py", "# note\ndef f():\n    return 1\n", True),
        ("a.py", "x = 1\n\ndef f():\n    return 1\n", False),
        ("a.py", "# far\n\ndef f():\n    return 1\n", False),
        ("a.js", "// note\nexport function f() {}\n", True),
        ("a.js", "export function f() {}\n", False),
        ("a.ts", "/** note */\nexport const f = () => 1;\n", True),
        ("A.java", "class A {\n  /** note */\n  public void m() {}\n}\n", True),
        ("A.java", "class A {\n  public void m() {}\n}\n", False),
        ("a.go", "package p\n\n// F does it.\nfunc F() {}\n", True),
        ("a.go", "package p\n\nfunc F() {}\n", False),
    ],
)
def test_the_reader_tells_documented_symbols_from_the_rest(
    path: str, source: str, documented: bool
) -> None:
    found = symbols_in(path, source)
    assert found is not None
    assert [s.documented for s in found if s.name.endswith(("f", "F", "m"))] == [documented]
