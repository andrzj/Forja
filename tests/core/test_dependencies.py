"""Installed dependencies are linked into a worktree and are never part of a change."""

import os
import sys
from pathlib import Path

import pytest

from forja.core.dependencies import is_dependency, link_dependencies, unlink_dependencies


def installed(root: Path) -> Path:
    (root / "node_modules" / "lib").mkdir(parents=True)
    (root / "node_modules" / "lib" / "index.js").write_text("x\n", encoding="utf-8")
    return root


def test_the_linked_dependencies_can_be_read_from_the_worktree(tmp_path: Path) -> None:
    source, target = installed(tmp_path / "repo"), tmp_path / "wt"
    target.mkdir()

    link_dependencies(source, target)

    assert (target / "node_modules" / "lib" / "index.js").read_text(encoding="utf-8") == "x\n"


def test_a_repository_without_dependencies_links_nothing(tmp_path: Path) -> None:
    (tmp_path / "repo").mkdir()
    (tmp_path / "wt").mkdir()

    link_dependencies(tmp_path / "repo", tmp_path / "wt")

    assert os.listdir(tmp_path / "wt") == []


def test_unlinking_leaves_the_installed_packages_alone(tmp_path: Path) -> None:
    source, target = installed(tmp_path / "repo"), tmp_path / "wt"
    target.mkdir()
    link_dependencies(source, target)

    unlink_dependencies(target)

    assert (source / "node_modules" / "lib" / "index.js").is_file()
    assert not (target / "node_modules").is_symlink()
    assert not (target / "node_modules").is_junction()


def test_a_path_is_a_dependency_when_it_is_or_lies_under_a_dependency_directory() -> None:
    assert is_dependency("node_modules")
    assert is_dependency("node_modules/lib/index.js")
    assert is_dependency("node_modules\\lib")
    assert not is_dependency("src/node_modules.js")
    assert is_dependency("web/node_modules/lib.js")
    assert is_dependency("a/b/node_modules")
    assert not is_dependency("web/src/node_modules.js")


def test_every_project_directory_with_dependencies_gets_its_own_link(tmp_path: Path) -> None:
    source, target = tmp_path / "repo", tmp_path / "wt"
    installed(source / "web")
    installed(source / "tools" / "ui")
    for where in ("web", "tools/ui"):
        (target / where).mkdir(parents=True)

    link_dependencies(source, target)

    assert (target / "web" / "node_modules" / "lib" / "index.js").is_file()
    assert (target / "tools" / "ui" / "node_modules" / "lib" / "index.js").is_file()
    unlink_dependencies(target)
    assert not (target / "web" / "node_modules").exists()
    assert not (target / "tools" / "ui" / "node_modules").exists()
    assert (source / "web" / "node_modules" / "lib" / "index.js").is_file()


def test_dependencies_of_a_directory_the_worktree_lacks_are_left_out(tmp_path: Path) -> None:
    source, target = tmp_path / "repo", tmp_path / "wt"
    installed(source / "web")
    target.mkdir()

    link_dependencies(source, target)

    assert os.listdir(target) == []


def _linked(source: Path, target: Path) -> None:
    link_dependencies(source, target)


def test_a_directory_of_the_worktree_that_is_a_link_gets_no_dependencies(tmp_path: Path) -> None:
    source, target = tmp_path / "repo", tmp_path / "wt"
    installed(source / "web")
    (target / "real").mkdir(parents=True)
    try:
        os.symlink(target / "real", target / "web", target_is_directory=True)
    except OSError:
        pytest.skip("no right to make links")

    _linked(source, target)

    assert not (target / "real" / "node_modules").exists()


def test_a_directory_below_a_link_that_leaves_the_worktree_gets_no_dependencies(
    tmp_path: Path,
) -> None:
    source, target, outside = tmp_path / "repo", tmp_path / "wt", tmp_path / "outside"
    installed(source / "x" / "y")
    (outside / "y").mkdir(parents=True)
    target.mkdir()
    try:
        os.symlink(outside, target / "x", target_is_directory=True)
    except OSError:
        pytest.skip("no right to make links")

    _linked(source, target)

    assert not (outside / "y" / "node_modules").exists()


def test_without_a_link_the_dependencies_are_copied(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, target = installed(tmp_path / "repo"), tmp_path / "wt"
    target.mkdir()

    def refuse(*args: object, **kwargs: object) -> None:
        raise OSError("no links")

    monkeypatch.setattr(os, "symlink", refuse)
    monkeypatch.setattr(sys, "platform", "linux")

    _linked(source, target)

    assert (target / "node_modules" / "lib" / "index.js").read_text(encoding="utf-8") == "x\n"
    assert not (target / "node_modules").is_symlink()


def test_the_link_is_made_as_a_link_to_a_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, target = installed(tmp_path / "repo"), tmp_path / "wt"
    target.mkdir()
    seen: list[dict[str, object]] = []
    real = os.symlink

    def spy(src: object, dst: object, **kwargs: object) -> None:
        seen.append(kwargs)
        real(src, dst, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(os, "symlink", spy)

    link_dependencies(source, target)

    assert seen == [{"target_is_directory": True}]


def test_a_copy_keeps_the_links_inside_the_packages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, target = installed(tmp_path / "repo"), tmp_path / "wt"
    target.mkdir()
    try:
        os.symlink("index.js", source / "node_modules" / "lib" / "alias.js")
    except OSError:
        pytest.skip("no right to make links")
    real = os.symlink

    def refuse_directories(src: object, dst: object, **kwargs: object) -> None:
        if kwargs.get("target_is_directory"):
            raise OSError("no links to directories")
        real(src, dst)  # type: ignore[arg-type]

    monkeypatch.setattr(os, "symlink", refuse_directories)
    monkeypatch.setattr(sys, "platform", "linux")

    link_dependencies(source, target)

    assert not (target / "node_modules").is_symlink()
    assert (target / "node_modules" / "lib" / "alias.js").is_symlink()


class _Done:
    def __init__(self, code: int) -> None:
        self.returncode = code


@pytest.mark.parametrize(("code", "copied"), [(0, False), (1, True)])
def test_on_windows_a_junction_is_tried_before_a_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, code: int, copied: bool
) -> None:
    source, target = installed(tmp_path / "repo"), tmp_path / "wt"
    target.mkdir()
    calls: list[list[str]] = []
    options: list[dict[str, object]] = []

    def run(command: list[str], **kwargs: object) -> _Done:
        calls.append(command)
        options.append(kwargs)
        return _Done(code)

    monkeypatch.setattr(os, "symlink", lambda *a, **k: (_ for _ in ()).throw(OSError("no")))
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr("forja.core.dependencies.subprocess.run", run)

    link_dependencies(source, target)

    assert [c[:3] for c in calls] == [["cmd", "/c", "mklink"]]
    assert options == [{"capture_output": True, "check": False}]
    assert (target / "node_modules" / "lib" / "index.js").exists() is copied
