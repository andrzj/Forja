"""The properties check: production code changed without a property test of its language."""

import asyncio
from pathlib import Path

import pytest

from forja.checks.changes import Change, ChangeKind, Changes
from forja.checks.properties import PropertiesCheck, library_of
from forja.core.gates import Approved, GateInput, GateResult, Inconclusive
from forja.core.gates.models import Rejected


def judge(tmp_path: Path, production: tuple[str, ...], tests: dict[str, str | None]) -> GateResult:
    """``tests`` maps a changed test file to its text; ``None`` leaves it without a file."""
    for path, text in tests.items():
        if text is not None:
            (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
            (tmp_path / path).write_text(text, encoding="utf-8")
    changes = Changes(tuple(Change(ChangeKind.ADDED, p) for p in (*production, *tests)), 0, ())
    check = PropertiesCheck(tmp_path, changes, production, lambda p: p in tests)
    return asyncio.run(check.evaluate(GateInput(tmp_path, "c" * 40, "t", "s", "a")))


@pytest.mark.parametrize(
    ("source", "test", "text"),
    [
        ("src/a.py", "tests/test_a.py", "from hypothesis import given\n"),
        ("src/a.ts", "tests/a.test.ts", "import fc from 'fast-check'\n"),
        ("pkg/a.go", "pkg/a_test.go", 'import "pgregory.net/rapid"\n'),
        ("src/A.cs", "tests/ATests.cs", "using FsCheck;\n"),
    ],
)
def test_a_changed_test_that_cites_the_library_of_the_language_approves(
    tmp_path: Path, source: str, test: str, text: str
) -> None:
    assert isinstance(judge(tmp_path, (source,), {test: text}), Approved)


@pytest.mark.parametrize(
    ("source", "test", "word"),
    [
        ("src/a.py", "tests/test_a.py", "python"),
        ("src/a.tsx", "tests/a.test.ts", "typescript"),
        ("pkg/a.go", "pkg/a_test.go", "go"),
        ("src/A.cs", "tests/ATests.cs", "csharp"),
    ],
)
def test_production_changed_without_a_property_test_is_one_finding(
    tmp_path: Path, source: str, test: str, word: str
) -> None:
    result = judge(tmp_path, (source,), {test: "plain example test\n"})

    assert isinstance(result, Rejected)
    assert [(f.target, f.measured, f.limit) for f in result.findings] == [(source, 0, 1)]
    assert word in result.findings[0].message


def test_no_changed_test_at_all_is_also_a_finding(tmp_path: Path) -> None:
    assert isinstance(judge(tmp_path, ("src/a.py",), {}), Rejected)


def test_the_library_of_another_language_does_not_count(tmp_path: Path) -> None:
    result = judge(tmp_path, ("src/a.py",), {"tests/a.test.ts": "import 'fast-check'\n"})

    assert isinstance(result, Rejected)


def test_each_language_with_changed_production_is_asked_once(tmp_path: Path) -> None:
    result = judge(
        tmp_path,
        ("src/a.py", "src/b.py", "pkg/a.go"),
        {"tests/test_a.py": "from hypothesis import given\n"},
    )

    assert isinstance(result, Rejected)
    assert [f.target for f in result.findings] == ["pkg/a.go"]


def test_production_in_a_language_without_a_library_asks_for_nothing(tmp_path: Path) -> None:
    assert isinstance(judge(tmp_path, ("src/A.java", "README.md"), {}), Approved)


def test_a_test_file_the_check_cannot_read_leaves_it_inconclusive(tmp_path: Path) -> None:
    result = judge(tmp_path, ("src/a.py",), {"tests/test_a.py": None})

    assert isinstance(result, Inconclusive)
    assert "tests/test_a.py" in result.detail


def test_an_unreadable_test_file_does_not_matter_when_the_library_was_found(
    tmp_path: Path,
) -> None:
    tests = {"tests/test_a.py": "import hypothesis\n", "tests/test_b.py": None}

    assert isinstance(judge(tmp_path, ("src/a.py",), tests), Approved)


def test_the_suffix_decides_the_library_whatever_its_case() -> None:
    assert library_of("A.GO") is library_of("a.go")
    assert library_of("a.go") is not None
    assert library_of("Makefile") is None
