"""Installed dependencies are linked into a worktree and are never part of a change."""

import os
from pathlib import Path

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
