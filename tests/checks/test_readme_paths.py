"""What a README names is text from the repository: it never reaches outside the worktree."""

import os
from pathlib import Path

import pytest

from forja.checks.readme_gate import exists_inside, inside, read_readme, readme_path
from forja.core.artifacts.models import Producer
from forja.core.redaction import Redactor
from forja.orchestrator.agent_runner import build_package
from forja.orchestrator.ports import AttemptContext, TaskInfo

TOKEN = "ghp_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"


def link_or_skip(link: Path, target: Path) -> None:
    try:
        os.symlink(target, link, target_is_directory=target.is_dir())
    except (OSError, NotImplementedError):
        pytest.skip("this system does not let the test make a symbolic link")


def test_a_path_inside_the_worktree_is_seen_and_one_that_is_not_there_is_not(
    tmp_path: Path,
) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "a.md").write_text("a", encoding="utf-8")
    assert exists_inside(tmp_path, "docs/a.md")
    assert exists_inside(tmp_path, "docs")
    assert not exists_inside(tmp_path, "docs/none.md")


@pytest.mark.parametrize("path", ["../outside.txt", "docs/../../outside.txt", "/etc/hosts", "C:/x"])
def test_a_path_that_goes_out_or_is_absolute_is_never_seen(tmp_path: Path, path: str) -> None:
    (tmp_path.parent / "outside.txt").write_text("x", encoding="utf-8")
    assert not exists_inside(tmp_path, path)
    assert inside(tmp_path, path) is None


def test_a_path_through_a_link_that_leaves_the_worktree_is_never_seen(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("x", encoding="utf-8")
    work = tmp_path / "work"
    work.mkdir()
    link_or_skip(work / "out", outside)
    assert not exists_inside(work, "out/secret.txt")


def test_a_readme_that_is_a_link_is_no_readme(tmp_path: Path) -> None:
    outside = tmp_path / "outside.md"
    outside.write_text("# secret", encoding="utf-8")
    work = tmp_path / "work"
    work.mkdir()
    link_or_skip(work / "README.md", outside)
    assert readme_path(work) is None
    assert read_readme(work) == (None, None)


def test_what_is_wrong_with_the_readme_is_redacted_before_it_reaches_the_agent(
    tmp_path: Path,
) -> None:
    task = TaskInfo("t1", "t1-d", "reduce", (), 3, 120, Producer.DOCUMENTER)
    report = f"- the build section cites make {TOKEN}; the project runs go build"
    ctx = AttemptContext(task, "t1-da1", tmp_path, None, readme=report)

    text = build_package(ctx, Redactor())

    assert TOKEN not in text
    assert "## README sections to fix" in text
    assert "the project runs go build" in text
    assert "## Files in scope" not in text


def test_the_worktree_itself_is_inside_it(tmp_path: Path) -> None:
    assert inside(tmp_path, ".") == tmp_path
    assert exists_inside(tmp_path, "")


def test_a_link_that_stays_inside_the_worktree_is_still_a_link(tmp_path: Path) -> None:
    (tmp_path / "real.md").write_text("x", encoding="utf-8")
    link_or_skip(tmp_path / "alias.md", tmp_path / "real.md")
    assert inside(tmp_path, "alias.md") is None
    assert not exists_inside(tmp_path, "alias.md")
