"""The private copy of the worktree that the checks measure the old version in."""

from pathlib import Path

from forja.checks.changes import Change, ChangeKind, Changes
from forja.checks.oldtree import old_tree


def test_the_copy_is_the_worktree_turned_back_into_the_old_texts(tmp_path: Path) -> None:
    work = tmp_path / "work"
    (work / "src").mkdir(parents=True)
    (work / ".git").mkdir()
    (work / ".git" / "HEAD").write_text("ref", encoding="utf-8")
    (work / "src" / "a.py").write_text("new", encoding="utf-8")
    (work / "src" / "kept.py").write_text("kept", encoding="utf-8")
    (work / "added.py").write_text("added", encoding="utf-8")
    (work / "renamed.py").write_text("renamed", encoding="utf-8")
    changes = Changes(
        (
            Change(ChangeKind.MODIFIED, "src/a.py"),
            Change(ChangeKind.ADDED, "added.py"),
            Change(ChangeKind.RENAMED, "renamed.py", "was.py"),
        ),
        0,
        (),
    )

    with old_tree(work, changes, {"src/a.py": "old", "was.py": "was"}, "forja-test-") as root:
        assert root.name.startswith("forja-test-") and root != work
        assert (root / "src" / "a.py").read_text(encoding="utf-8") == "old"
        assert (root / "src" / "kept.py").read_text(encoding="utf-8") == "kept"
        assert (root / "was.py").read_text(encoding="utf-8") == "was"
        assert not (root / "added.py").exists() and not (root / "renamed.py").exists()
        assert not (root / ".git").exists()
    assert not root.exists()
    assert (work / "src" / "a.py").read_text(encoding="utf-8") == "new"  # the worktree is untouched


def test_an_added_file_that_is_not_there_is_not_an_error(tmp_path: Path) -> None:
    (tmp_path / "work").mkdir()
    changes = Changes((Change(ChangeKind.ADDED, "gone.py"),), 0, ())

    with old_tree(tmp_path / "work", changes, {}) as root:
        assert root.is_dir()
