"""Reading what git says about a change: status, size, quoting, and the lines a patch adds."""

import asyncio
from pathlib import Path

import pytest

from forja.checks.changes import (
    AddedLine,
    Change,
    ChangeKind,
    Changes,
    added_lines,
    count_lines,
    parse_status,
    read_before,
    read_changes,
    unquote,
    write_files,
)
from forja.core.dependencies import link_dependencies
from tests.core.idempotency.conftest import Repo, repo  # noqa: F401 - the fixture is used below


def test_each_kind_of_status_line_becomes_a_change() -> None:
    lines = [
        "A\tnew.py",
        "M\tkept.py",
        "D\tgone.py",
        "R087\told.py\tmoved.py",
        "C100\tsource.py\tcopy.py",
        "T\tlink.py",
        "U\tconflict.py",
        "M",
        "R100\ttoo\tmany\tfields",
    ]

    assert parse_status(lines) == (
        Change(ChangeKind.ADDED, "new.py"),
        Change(ChangeKind.MODIFIED, "kept.py"),
        Change(ChangeKind.DELETED, "gone.py"),
        Change(ChangeKind.RENAMED, "moved.py", "old.py"),
        Change(ChangeKind.ADDED, "copy.py"),
        Change(ChangeKind.MODIFIED, "link.py"),
    )


def test_a_change_knows_where_its_content_came_from() -> None:
    assert Change(ChangeKind.ADDED, "a.py").before is None
    assert Change(ChangeKind.MODIFIED, "a.py").before == "a.py"
    assert Change(ChangeKind.DELETED, "a.py").before == "a.py"
    assert Change(ChangeKind.RENAMED, "b.py", "a.py").before == "a.py"
    assert Change(ChangeKind.DELETED, "a.py").exists_now is False
    assert Change(ChangeKind.RENAMED, "b.py", "a.py").exists_now is True


def test_only_files_that_exist_now_and_have_the_suffix_are_current() -> None:
    changes = Changes(
        (
            Change(ChangeKind.MODIFIED, "a.py"),
            Change(ChangeKind.DELETED, "b.py"),
            Change(ChangeKind.ADDED, "c.md"),
            Change(ChangeKind.RENAMED, "d.py", "x.py"),
        ),
        0,
        (),
    )

    assert changes.current((".py",)) == ("a.py", "d.py")
    assert changes.current() == ("a.py", "c.md", "d.py")
    assert changes.current(lambda path: not path.endswith(".py")) == ("c.md",)


@pytest.mark.parametrize(
    ("numstat", "total"),
    [
        (["3\t1\ta.py", "0\t4\tb.py"], 8),
        (["-\t-\timage.png", "2\t2\ta.py"], 4),
        (["3\t1\told => new"], 4),
        ([], 0),
        (["junk"], 0),
    ],
)
def test_the_size_of_a_change_is_the_lines_added_and_removed(
    numstat: list[str], total: int
) -> None:
    assert count_lines(numstat) == total


@pytest.mark.parametrize(
    ("quoted", "plain"),
    [
        ('"caf\\303\\251.py"', "café.py"),
        ('"with\\ttab.py"', "with\ttab.py"),
        ('"say \\"hi\\".py"', 'say "hi".py'),
        ('"back\\\\slash.py"', "back\\slash.py"),
        ('"line\\nbreak.py"', "line\nbreak.py"),
        ("plain.py", "plain.py"),
        ('"', '"'),
        ('"unterminated', '"unterminated'),
        ('"odd\\qescape"', "odd\\qescape"),
        ('"café"', "café"),
    ],
)
def test_the_quoting_git_adds_to_unusual_names_is_undone(quoted: str, plain: str) -> None:
    assert unquote(quoted) == plain


def test_added_lines_carry_the_file_and_the_line_they_land_on() -> None:
    patch = (
        "diff --git a/a.py b/a.py",
        "--- a/a.py",
        "+++ b/a.py",
        "@@ -3 +3,2 @@",
        "-old",
        "+new one",
        "+new two",
        "@@ -10,0 +12 @@",
        "+later",
        "diff --git a/b.py b/b.py",
        "--- /dev/null",
        "+++ b/b.py",
        "@@ -0,0 +1 @@",
        "+first",
    )

    assert added_lines(patch) == [
        AddedLine("a.py", 3, "new one"),
        AddedLine("a.py", 4, "new two"),
        AddedLine("a.py", 12, "later"),
        AddedLine("b.py", 1, "first"),
    ]


def test_an_added_line_that_looks_like_a_file_header_is_still_an_added_line() -> None:
    patch = (
        "diff --git a/a.py b/a.py",
        "--- a/a.py",
        "+++ b/a.py",
        "@@ -1,0 +2,2 @@",
        "+++ b/other.py",
        '+KEY = "x"',
    )

    assert added_lines(patch) == [
        AddedLine("a.py", 2, "++ b/other.py"),
        AddedLine("a.py", 3, 'KEY = "x"'),
    ]


def test_a_removed_line_that_looks_like_a_header_does_not_end_the_hunk() -> None:
    patch = (
        "diff --git a/a.py b/a.py",
        "--- a/a.py",
        "+++ b/a.py",
        "@@ -5,2 +5 @@",
        "--- not a header",
        "-gone",
        "+kept",
    )

    assert added_lines(patch) == [AddedLine("a.py", 5, "kept")]


def test_a_deleted_file_adds_nothing_and_a_hunk_header_without_counts_means_one_line() -> None:
    patch = (
        "--- a/gone.py",
        "+++ /dev/null",
        "@@ -1,2 +0,0 @@",
        "-a",
        "-b",
        "--- a/x.py",
        "+++ b/x.py",
        "@@ -7 +7 @@",
        "-old",
        "+new",
        "@@ nonsense @@",
        "+orphan",
    )

    assert added_lines(patch) == [AddedLine("x.py", 7, "new")]


# -- with git --------------------------------------------------------------------------------------


def test_git_is_asked_for_status_size_patch_and_ignored_files(repo: Repo) -> None:  # noqa: F811
    (repo.path / ".gitignore").write_text("*.local\n", encoding="utf-8")
    (repo.path / "kept.py").write_text("one\ntwo\n", encoding="utf-8")
    (repo.path / "old.py").write_text("a\nb\nc\nd\ne\nf\n", encoding="utf-8")
    repo.sh("add", "-A")
    repo.sh("commit", "-m", "start")
    (repo.path / "kept.py").write_text("one\ntwo\nthree\n", encoding="utf-8")
    repo.sh("mv", "old.py", "moved.py")
    (repo.path / "fresh.py").write_text("x\n", encoding="utf-8")
    (repo.path / "hidden.local").write_text("h\n", encoding="utf-8")

    changes = asyncio.run(read_changes(repo.git))

    assert sorted((c.kind.value, c.path, c.old_path) for c in changes.files) == [
        ("A", "fresh.py", None),
        ("M", "kept.py", None),
        ("R", "moved.py", "old.py"),
    ]
    assert changes.lines == 2
    assert [(a.path, a.number, a.text) for a in added_lines(changes.patch)] == [
        ("fresh.py", 1, "x"),
        ("kept.py", 3, "three"),
    ]
    assert changes.ignored == ("hidden.local",)


def test_the_work_can_be_read_against_an_earlier_commit_than_the_parent(repo: Repo) -> None:  # noqa: F811
    (repo.path / "a.py").write_text("one\n", encoding="utf-8")
    repo.sh("add", "-A")
    repo.sh("commit", "-m", "start")
    (repo.path / "a.py").write_text("one\ntwo\n", encoding="utf-8")
    repo.sh("commit", "-am", "code")
    (repo.path / "test_a.py").write_text("t\n", encoding="utf-8")

    own = asyncio.run(read_changes(repo.git))
    since = asyncio.run(read_changes(repo.git, "HEAD~1"))
    before = asyncio.run(read_before(repo.git, since, (".py",), "HEAD~1"))

    assert [c.path for c in own.files] == ["test_a.py"]
    assert sorted(c.path for c in since.files) == ["a.py", "test_a.py"]
    assert [(a.path, a.number) for a in added_lines(since.patch)] == [
        ("a.py", 2),
        ("test_a.py", 1),
    ]
    assert before == {"a.py": "one\n"}


def test_renames_are_found_even_when_the_user_turned_detection_off(repo: Repo) -> None:  # noqa: F811
    (repo.path / "old.py").write_text("a\nb\nc\nd\ne\nf\n", encoding="utf-8")
    repo.sh("add", "-A")
    repo.sh("commit", "-m", "start")
    repo.sh("config", "diff.renames", "false")
    repo.sh("mv", "old.py", "moved.py")

    changes = asyncio.run(read_changes(repo.git))

    assert [(c.kind.value, c.path, c.old_path) for c in changes.files] == [
        ("R", "moved.py", "old.py")
    ]
    assert changes.lines == 0


def test_the_parent_commits_text_is_read_by_the_old_path_and_written_elsewhere(
    repo: Repo,  # noqa: F811
    tmp_path: Path,
) -> None:
    (repo.path / "a.py").write_text("one\ntwo\n", encoding="utf-8")
    (repo.path / "notes.md").write_text("x\n", encoding="utf-8")
    repo.sh("add", "-A")
    repo.sh("commit", "-m", "start")
    repo.sh("mv", "a.py", "b.py")
    (repo.path / "notes.md").write_text("y\n", encoding="utf-8")
    changes = asyncio.run(read_changes(repo.git))

    contents = asyncio.run(read_before(repo.git, changes, (".py",)))
    write_files(contents, tmp_path / "out")

    assert contents == {"a.py": "one\ntwo\n"}
    assert asyncio.run(read_before(repo.git, changes, lambda path: path == "notes.md")) == {
        "notes.md": "x\n"
    }
    assert (tmp_path / "out" / "a.py").read_text(encoding="utf-8") == "one\ntwo\n"


def test_the_names_of_ignored_files_are_unquoted_like_the_others(repo: Repo) -> None:  # noqa: F811
    (repo.path / ".gitignore").write_text("*.local\n", encoding="utf-8")
    (repo.path / "kept.py").write_text("one\n", encoding="utf-8")
    repo.sh("add", "-A")
    repo.sh("commit", "-m", "start")
    (repo.path / "café.local").write_text("h\n", encoding="utf-8")

    changes = asyncio.run(read_changes(repo.git))

    assert changes.ignored == ("café.local",)


@pytest.mark.parametrize("ignore", ["", "node_modules\n"])
def test_the_linked_dependencies_are_not_a_change(repo: Repo, tmp_path: Path, ignore: str) -> None:  # noqa: F811
    installed = tmp_path / "installed"
    (installed / "node_modules" / "lib").mkdir(parents=True)
    (installed / "node_modules" / "lib" / "index.js").write_text("x\n", encoding="utf-8")
    (repo.path / ".gitignore").write_text(ignore, encoding="utf-8")
    repo.sh("add", "-A")
    repo.sh("commit", "-m", "start", "--allow-empty")
    link_dependencies(installed, repo.path)
    (repo.path / "fresh.py").write_text("x\n", encoding="utf-8")

    changes = asyncio.run(read_changes(repo.git))

    assert [c.path for c in changes.files] == ["fresh.py"]
    assert changes.ignored == ()


@pytest.mark.parametrize("ignore", ["", "node_modules\n"])
def test_the_dependencies_of_a_subproject_are_not_a_change(
    repo: Repo,  # noqa: F811
    tmp_path: Path,
    ignore: str,
) -> None:
    installed = tmp_path / "installed"
    (installed / "web" / "node_modules" / "lib").mkdir(parents=True)
    (installed / "web" / "node_modules" / "lib" / "index.js").write_text("x\n", encoding="utf-8")
    (repo.path / "web").mkdir()
    (repo.path / "web" / "package.json").write_text("{}\n", encoding="utf-8")
    (repo.path / ".gitignore").write_text(ignore, encoding="utf-8")
    repo.sh("add", "-A")
    repo.sh("commit", "-m", "start")
    link_dependencies(installed, repo.path)
    (repo.path / "web" / "fresh.ts").write_text("x\n", encoding="utf-8")

    changes = asyncio.run(read_changes(repo.git))

    assert [c.path for c in changes.files] == ["web/fresh.ts"]
    assert changes.ignored == ()


def test_the_example_database_of_hypothesis_is_not_a_change(repo: Repo) -> None:  # noqa: F811
    repo.sh("commit", "-m", "start", "--allow-empty")
    for where in (".hypothesis", "pkg/.hypothesis"):
        (repo.path / where / "examples").mkdir(parents=True)
        (repo.path / where / "examples" / "entry").write_text("x\n", encoding="utf-8")
    (repo.path / "fresh.py").write_text("x\n", encoding="utf-8")

    changes = asyncio.run(read_changes(repo.git))

    assert [c.path for c in changes.files] == ["fresh.py"]
    assert changes.ignored == ()
