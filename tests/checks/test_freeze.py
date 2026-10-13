"""The implementer finds the test author's tests exactly as they were committed."""

import asyncio
from pathlib import Path

from forja.checks.changes import Change, ChangeKind, Changes
from forja.checks.freeze import FreezeCheck, tree_digest
from forja.core.gates import Approved, GateInput, Rejected

NOTHING = Changes((), 0, ())
DATA = GateInput(Path("."), "c" * 40, "t1", "t1-s", "t1-a1")


def write(root: Path, name: str, text: str = "x") -> None:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def frozen(tmp_path: Path) -> str:
    write(tmp_path, "tests/test_a.py", "def test_a(): ...\n")
    write(tmp_path, "tests/data/case.json", "{}")
    write(tmp_path, "src/a.py", "x = 1\n")
    return tree_digest(tmp_path, "tests")


def judge(tmp_path: Path, digest: str, changes: Changes = NOTHING) -> list[str] | None:
    result = asyncio.run(FreezeCheck(tmp_path, changes, "tests", digest).evaluate(DATA))
    if isinstance(result, Approved):
        return None
    assert isinstance(result, Rejected)
    return [f.describe() for f in result.findings]


def test_tests_left_as_they_were_are_approved(tmp_path: Path) -> None:
    digest = frozen(tmp_path)
    write(tmp_path, "src/a.py", "x = 2\n")

    assert judge(tmp_path, digest) is None


def test_a_cache_the_tools_leave_under_the_tests_is_not_a_change(tmp_path: Path) -> None:
    digest = frozen(tmp_path)
    write(tmp_path, "tests/__pycache__/test_a.cpython-312.pyc", "bytes")
    write(tmp_path, "tests/.pytest_cache/v/cache", "bytes")

    assert judge(tmp_path, digest) is None


def test_a_changed_test_is_named(tmp_path: Path) -> None:
    digest = frozen(tmp_path)
    write(tmp_path, "tests/test_a.py", "def test_a(): assert True\n")
    changes = Changes((Change(ChangeKind.MODIFIED, "tests/test_a.py"),), 1, ())

    assert judge(tmp_path, digest, changes) == ["a frozen test file was changed [tests/test_a.py]"]


def test_a_deleted_test_is_named(tmp_path: Path) -> None:
    digest = frozen(tmp_path)
    (tmp_path / "tests" / "test_a.py").unlink()
    changes = Changes((Change(ChangeKind.DELETED, "tests/test_a.py"),), 1, ())

    assert judge(tmp_path, digest, changes) == ["a frozen test file was changed [tests/test_a.py]"]


def test_a_test_moved_out_of_the_tests_is_named_by_its_old_path(tmp_path: Path) -> None:
    digest = frozen(tmp_path)
    (tmp_path / "tests" / "test_a.py").rename(tmp_path / "src" / "test_a.py")
    changes = Changes((Change(ChangeKind.RENAMED, "src/test_a.py", "tests/test_a.py"),), 1, ())

    assert judge(tmp_path, digest, changes) == ["a frozen test file was changed [tests/test_a.py]"]


def test_a_new_file_that_git_ignores_is_named(tmp_path: Path) -> None:
    digest = frozen(tmp_path)
    write(tmp_path, "tests/conftest.py", "import os\n")
    changes = Changes((), 0, (), ("tests/conftest.py",))

    assert judge(tmp_path, digest, changes) == [
        "a frozen test file was changed [tests/conftest.py]"
    ]


def test_a_change_nobody_listed_still_rejects(tmp_path: Path) -> None:
    digest = frozen(tmp_path)
    write(tmp_path, "tests/data/case.json", "[]")

    assert judge(tmp_path, digest) == ["the frozen tests were changed [tests]"]


def test_removing_the_whole_directory_is_a_change(tmp_path: Path) -> None:
    digest = frozen(tmp_path)
    for path in sorted((tmp_path / "tests").rglob("*"), reverse=True):
        path.unlink() if path.is_file() else path.rmdir()
    (tmp_path / "tests").rmdir()

    assert judge(tmp_path, digest) == ["the frozen tests were changed [tests]"]
