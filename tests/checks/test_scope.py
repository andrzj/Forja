"""Gate 1 on hand-made changes: what may change, how much, and what was declared."""

import asyncio
from pathlib import Path

import pytest

from forja.checks.changes import Change, ChangeKind, Changes
from forja.checks.scope import ScopeCheck, disposable, in_scope
from forja.core.adapters import FileClass
from forja.core.gates import Approved, GateInput, Rejected
from forja.languages.python import PythonAdapter
from forja.orchestrator.ports import TaskInfo

ADAPTER = PythonAdapter()


def classify(path: str) -> FileClass:
    return ADAPTER.classify(path) or FileClass.OTHER


def modified(
    *paths: str, lines: int = 3, patch: tuple[str, ...] = (), ignored: tuple[str, ...] = ()
) -> Changes:
    return Changes(tuple(Change(ChangeKind.MODIFIED, p) for p in paths), lines, patch, ignored)


def evaluate(
    changes: Changes,
    *,
    scope: tuple[str, ...] = ("src/a.py",),
    max_files: int = 8,
    max_lines: int = 400,
    declared: tuple[str, ...] = (),
    values: dict | None = None,  # type: ignore[type-arg]
):  # type: ignore[no-untyped-def]
    task = TaskInfo("t1", "t1-s", "intent", scope, max_files, max_lines)
    data = GateInput(Path("."), "c" * 40, "t1", "t1-s", "t1-a1", values=values or {})
    return asyncio.run(ScopeCheck(changes, task, classify, declared).evaluate(data))


def described(result: object) -> list[str]:
    assert isinstance(result, Rejected)
    return [f.describe() for f in result.findings]


@pytest.mark.parametrize(
    ("path", "scope", "expected"),
    [
        ("src/a.py", ("src/a.py",), True),
        ("src/a.py", ("src",), True),
        ("src/a.py", ("src/",), True),
        ("src\\a.py", ("src/a.py",), True),
        ("src/a.py", ("src\\",), True),
        ("src/ab.py", ("src/a",), False),
        ("src/a.py", ("src/b.py",), False),
        ("other/a.py", ("src",), False),
        ("src/a.py", (), False),
    ],
)
def test_a_path_is_in_scope_when_it_is_an_entry_or_lies_under_one(
    path: str, scope: tuple[str, ...], expected: bool
) -> None:
    assert in_scope(path, scope) is expected


def test_a_change_inside_the_scope_is_approved() -> None:
    assert evaluate(modified("src/a.py")) == Approved()


def test_every_kind_of_file_outside_a_refactoring_is_named_for_what_it_is() -> None:
    changes = modified(
        "src/a.py", "tests/test_a.py", "tests/fixtures/data.py", "pyproject.toml", "docs/x.md"
    )

    rule = "only production files may change in a refactoring"

    assert described(evaluate(changes, scope=("src", "tests", "docs", "pyproject.toml"))) == [
        f"{rule} (this is test) [tests/test_a.py]",
        f"{rule} (this is fixture) [tests/fixtures/data.py]",
        f"{rule} (this is other) [pyproject.toml]",
        f"{rule} (this is other) [docs/x.md]",
    ]


def test_a_production_file_outside_the_scope_is_named() -> None:
    assert described(evaluate(modified("src/a.py", "src/b.py"))) == [
        "outside the task scope [src/b.py]"
    ]


def test_a_rename_counts_both_ends_once() -> None:
    changes = Changes((Change(ChangeKind.RENAMED, "src/new.py", "src/old.py"),), 2, ())

    assert described(evaluate(changes, scope=("src/old.py",))) == [
        "outside the task scope [src/new.py]"
    ]
    assert evaluate(changes, scope=("src",)) == Approved()


def test_a_change_of_nothing_is_rejected() -> None:
    assert described(evaluate(Changes((), 0, ()))) == ["the attempt changed nothing [diff]"]


def test_the_limits_of_the_task_are_enforced_with_the_numbers() -> None:
    changes = modified("src/a.py", "src/b.py", "src/c.py", lines=50)

    assert described(evaluate(changes, scope=("src",), max_files=2, max_lines=10)) == [
        "more files changed than the task allows [diff] measured 3, limit 2",
        "more lines changed than the task allows [diff] measured 50, limit 10",
    ]


def test_staying_exactly_at_the_limit_is_allowed() -> None:
    changes = modified("src/a.py", "src/b.py", lines=10)

    assert evaluate(changes, scope=("src",), max_files=2, max_lines=10) == Approved()


def test_the_policy_limit_applies_when_the_task_has_none_and_the_stricter_one_wins() -> None:
    changes = modified("src/a.py", "src/b.py", lines=50)
    policy = {"limits": {"max_files": 1, "max_lines": 20}}

    assert described(
        evaluate(changes, scope=("src",), max_files=0, max_lines=0, values=policy)
    ) == [
        "more files changed than the task allows [diff] measured 2, limit 1",
        "more lines changed than the task allows [diff] measured 50, limit 20",
    ]
    assert described(
        evaluate(changes, scope=("src",), max_files=5, max_lines=30, values=policy)
    ) == [
        "more files changed than the task allows [diff] measured 2, limit 1",
        "more lines changed than the task allows [diff] measured 50, limit 20",
    ]
    assert described(
        evaluate(changes, scope=("src",), max_files=1, max_lines=10, values=policy)
    ) == [
        "more files changed than the task allows [diff] measured 2, limit 1",
        "more lines changed than the task allows [diff] measured 50, limit 10",
    ]


@pytest.mark.parametrize(
    "limits", [{"max_files": 0}, {"max_files": -1}, {"max_files": "9"}, "x", None]
)
def test_a_limit_that_is_not_a_positive_number_is_not_one(limits: object) -> None:
    changes = modified("src/a.py", "src/b.py", "src/c.py")

    assert evaluate(changes, scope=("src",), max_files=0, values={"limits": limits}) == Approved()


def test_declared_files_must_be_the_changed_ones() -> None:
    changes = modified("src/a.py", "src/b.py")

    assert evaluate(changes, scope=("src",), declared=("src/a.py", "src/b.py")) == Approved()
    assert evaluate(changes, scope=("src",), declared=("src\\a.py", "src\\b.py")) == Approved()
    assert described(evaluate(changes, scope=("src",), declared=("src/a.py", "src/c.py"))) == [
        "the declared files differ from the changed ones "
        "(declared but not changed: src/c.py; changed but not declared: src/b.py) [diff]"
    ]
    assert described(evaluate(changes, scope=("src",), declared=("src/a.py",))) == [
        "the declared files differ from the changed ones "
        "(changed but not declared: src/b.py) [diff]"
    ]
    assert described(
        evaluate(modified("src/a.py"), scope=("src",), declared=("src/a.py", "src/z.py"))
    ) == [
        "the declared files differ from the changed ones "
        "(declared but not changed: src/z.py) [diff]"
    ]


def test_ignored_files_are_hidden_unless_they_are_what_tools_leave_behind() -> None:
    changes = modified(
        "src/a.py",
        ignored=("a.local", "src/__pycache__/a.cpython-312.pyc", "stray.pyc", ".ruff_cache/z"),
    )

    assert described(evaluate(changes)) == [
        "a file git ignores was added [a.local]",
        "a file git ignores was added [stray.pyc]",
    ]


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("src/__pycache__/a.cpython-312.pyc", True),
        ("src\\__pycache__\\a.cpython-312.pyc", True),
        ("src/__pycache__/a.cpython-312.opt-1.pyo", True),
        (".pytest_cache/v/cache/lastfailed", True),
        (".ruff_cache/0.1/data", True),
        (".mypy_cache/3.12/x.json", True),
        (".hypothesis/examples/x", True),
        ("stray.pyc", False),
        ("src/stray.pyo", False),
        ("src/__pycache__/evil.py", False),
        ("src/__pycache__/evil.pyi", False),
        (".ruff_cache/hook.pth", False),
        (".ruff_cache/native.so", False),
        (".ruff_cache/native.pyd", False),
        ("__pycache__", False),
        ("a.local", False),
        ("not__pycache__/x.txt", False),
    ],
)
def test_only_what_a_tool_caches_is_disposable(path: str, expected: bool) -> None:
    assert disposable(path) is expected


PATCH = (
    "diff --git a/src/a.py b/src/a.py",
    "--- a/src/a.py",
    "+++ b/src/a.py",
    "@@ -1 +1,2 @@",
    "-old",
    "+new  # noqa",
    "+fine",
)


def test_a_silencing_comment_is_found_in_the_added_lines_only() -> None:
    assert described(evaluate(modified("src/a.py", patch=PATCH))) == [
        "a comment that silences a tool was added [src/a.py]"
    ]
    removed = ("--- a/src/a.py", "+++ b/src/a.py", "@@ -1 +1 @@", "-old  # noqa", "+new")
    assert evaluate(modified("src/a.py", patch=removed)) == Approved()


def test_findings_are_gathered_from_every_rule_at_once() -> None:
    changes = modified("src/a.py", "src/b.py", lines=999, patch=PATCH, ignored=("c.local",))

    assert len(described(evaluate(changes, max_files=1, declared=("src/q.py",)))) == 6


@pytest.mark.parametrize(
    "marker",
    [
        "x = 1  # noqa: E501",
        "x = 1  # NOQA",
        "# ruff: noqa",
        "# fmt: off",
        "# fmt:on",
        "x = 1  # fmt: skip",
        "# yapf: disable",
        "# yapf:enable",
        'KEY = "x"  # gitleaks:allow',
        "def f():  # lizard forgives",
        "def f():  # lizard forgive",
        "# lizard: ignore",
        "# GENERATED CODE",
        "# generated   code",
        "x = 1  # nosem",
        "x = 1  # nosemgrep",
    ],
)
def test_every_comment_that_switches_a_tool_off_is_found(marker: str) -> None:
    patch = ("--- a/src/a.py", "+++ b/src/a.py", "@@ -0,0 +1 @@", f"+{marker}")

    assert described(evaluate(modified("src/a.py", patch=patch))) == [
        "a comment that silences a tool was added [src/a.py]"
    ]


@pytest.mark.parametrize("fine", ["x = 1  # a normal comment", "# format the output", "y = 'fmt'"])
def test_an_ordinary_comment_is_not_a_silencer(fine: str) -> None:
    patch = ("--- a/src/a.py", "+++ b/src/a.py", "@@ -0,0 +1 @@", f"+{fine}")

    assert evaluate(modified("src/a.py", patch=patch)) == Approved()
