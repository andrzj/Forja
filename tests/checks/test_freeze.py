"""The implementer finds the test author's tests exactly as they were committed."""

import asyncio
from pathlib import Path

from forja.checks.changes import Change, ChangeKind, Changes
from forja.checks.freeze import AppendOnlyCheck, FreezeCheck, frozen_digest_of
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
    return frozen_digest_of(tmp_path, "tests", ())


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


def append_only(*changes: Change) -> list[str] | None:
    result = asyncio.run(AppendOnlyCheck(Changes(changes, 0, ()), "tests").evaluate(DATA))
    if isinstance(result, Approved):
        return None
    assert isinstance(result, Rejected)
    return [f.target for f in result.findings]


def test_an_extra_test_stage_may_add_tests_and_change_the_code() -> None:
    assert (
        append_only(
            Change(ChangeKind.ADDED, "tests/test_new.py"), Change(ChangeKind.MODIFIED, "src/a.py")
        )
        is None
    )


def test_an_extra_test_stage_may_not_change_move_or_delete_an_existing_test() -> None:
    assert append_only(Change(ChangeKind.MODIFIED, "tests/test_a.py")) == ["tests/test_a.py"]
    assert append_only(Change(ChangeKind.DELETED, "tests/test_a.py")) == ["tests/test_a.py"]
    assert append_only(Change(ChangeKind.RENAMED, "tests/test_b.py", "tests/test_a.py")) == [
        "tests/test_a.py",
        "tests/test_b.py",
    ]


def beside_the_code(name: str) -> bool:
    return name.endswith("_test.go")


def frozen_beside_the_code(tmp_path: Path) -> tuple[str, tuple[str, ...]]:
    write(tmp_path, "pkg/a.go", "package pkg\n")
    write(tmp_path, "pkg/a_test.go", "package pkg\n")
    tests = ("pkg/a_test.go",)
    return frozen_digest_of(tmp_path, "", tests), tests


def judge_beside_the_code(
    tmp_path: Path, digest: str, tests: tuple[str, ...], changes: Changes = NOTHING
) -> list[str] | None:
    check = FreezeCheck(tmp_path, changes, "", digest, tests, beside_the_code)
    result = asyncio.run(check.evaluate(DATA))
    if isinstance(result, Approved):
        return None
    assert isinstance(result, Rejected)
    return [f.describe() for f in result.findings]


def test_tests_beside_the_code_are_frozen_without_a_tests_root(tmp_path: Path) -> None:
    digest, tests = frozen_beside_the_code(tmp_path)
    write(tmp_path, "pkg/a.go", "package pkg // changed\n")
    assert judge_beside_the_code(tmp_path, digest, tests) is None

    write(tmp_path, "pkg/a_test.go", "package pkg // changed\n")
    changes = Changes((Change(ChangeKind.MODIFIED, "pkg/a_test.go"),), 1, ())

    assert judge_beside_the_code(tmp_path, digest, tests, changes) == [
        "a frozen test file was changed [pkg/a_test.go]"
    ]


def test_a_test_file_added_beside_the_code_is_a_change(tmp_path: Path) -> None:
    digest, _ = frozen_beside_the_code(tmp_path)
    write(tmp_path, "pkg/b_test.go", "package pkg\n")
    changes = Changes((Change(ChangeKind.ADDED, "pkg/b_test.go"),), 1, ())

    assert judge_beside_the_code(tmp_path, digest, ("pkg/a_test.go", "pkg/b_test.go"), changes) == [
        "a frozen test file was changed [pkg/b_test.go]"
    ]


def test_a_test_renamed_to_a_production_name_is_a_change(tmp_path: Path) -> None:
    digest, _ = frozen_beside_the_code(tmp_path)
    (tmp_path / "pkg" / "a_test.go").rename(tmp_path / "pkg" / "b.go")
    changes = Changes((Change(ChangeKind.RENAMED, "pkg/b.go", "pkg/a_test.go"),), 1, ())

    assert judge_beside_the_code(tmp_path, digest, (), changes) == [
        "a frozen test file was changed [pkg/a_test.go]"
    ]


def test_an_extra_test_stage_beside_the_code_may_only_add_test_files() -> None:
    def judged(*changes: Change) -> list[str] | None:
        check = AppendOnlyCheck(Changes(changes, 0, ()), "", beside_the_code)
        result = asyncio.run(check.evaluate(DATA))
        if isinstance(result, Approved):
            return None
        assert isinstance(result, Rejected)
        return [f.target for f in result.findings]

    assert judged(Change(ChangeKind.ADDED, "pkg/b_test.go")) is None
    assert judged(Change(ChangeKind.MODIFIED, "pkg/a_test.go")) == ["pkg/a_test.go"]
    assert judged(Change(ChangeKind.MODIFIED, "pkg/a.go")) is None


def test_a_change_nobody_listed_beside_the_code_names_the_tests_as_the_target(
    tmp_path: Path,
) -> None:
    digest, tests = frozen_beside_the_code(tmp_path)
    write(tmp_path, "pkg/a_test.go", "package pkg // changed\n")

    assert judge_beside_the_code(tmp_path, digest, tests) == [
        "the frozen tests were changed [tests]"
    ]


def test_line_endings_alone_do_not_count_as_a_change(tmp_path: Path) -> None:
    frozen(tmp_path)
    (tmp_path / "tests/test_a.py").write_bytes(b"def test_a(): ...\n")
    digest = frozen_digest_of(tmp_path, "tests", ())
    (tmp_path / "tests/test_a.py").write_bytes(b"def test_a(): ...\r\n")

    assert judge(tmp_path, digest) is None


def test_a_change_of_text_is_still_a_change_under_other_line_endings(tmp_path: Path) -> None:
    frozen(tmp_path)
    (tmp_path / "tests/test_a.py").write_bytes(b"def test_a(): ...\n")
    digest = frozen_digest_of(tmp_path, "tests", ())
    (tmp_path / "tests/test_a.py").write_bytes(b"def test_b(): ...\r\n")

    assert judge(tmp_path, digest) == ["the frozen tests were changed [tests]"]


def test_a_binary_file_is_hashed_as_it_is(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/blob.bin").write_bytes(b"a\r\nb\x00")
    digest = frozen_digest_of(tmp_path, "tests", ())
    (tmp_path / "tests/blob.bin").write_bytes(b"a\nb\x00")

    assert frozen_digest_of(tmp_path, "tests", ()) != digest
