"""Installed dependencies are the project's environment, not part of its tests or of a change.

A worktree has none of them, because git does not carry them; they are linked in from the
repository, and every check that reads the worktree's changes leaves them out.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Protocol

from forja.core.adapters.projects import project_directories

DEPENDENCY_DIRS = ("node_modules",)


class _Git(Protocol):
    async def lines(self, *args: str) -> list[str]: ...


async def stage_all(git: _Git) -> None:
    """Stage everything in the worktree but the dependencies, at any depth: a link that git does
    not ignore would otherwise be added (an exclude pathspec makes git fail when the path is
    ignored)."""
    await git.lines("add", "-A")
    # the link itself, and what lies under it when it is a directory the platform lets git walk
    pathspecs = (f":(glob)**/{name}{tail}" for name in DEPENDENCY_DIRS for tail in ("", "/**"))
    await git.lines("reset", "-q", "--", *pathspecs)


def is_dependency(path: str) -> bool:
    """Whether ``path`` is one of the dependency directories or lies under one, at any depth."""
    return any(part in DEPENDENCY_DIRS for part in path.replace("\\", "/").split("/"))


def link_dependencies(source: Path, target: Path) -> None:
    """Let ``target`` use the dependencies installed in ``source`` without copying them: a link,
    a junction where Windows allows no link, a copy as the last resort. Every project directory
    that has them gets its own; one whose directory the worktree lacks is left out."""
    for directory in project_directories(source):
        where = directory.relative_to(source)
        if not (target / where).is_dir():
            continue
        for name in DEPENDENCY_DIRS:
            packages = directory / name
            if packages.is_dir():
                _link(packages, target / where / name)


def _link(packages: Path, link: Path) -> None:
    try:
        os.symlink(packages, link, target_is_directory=True)
        return
    except OSError:
        pass
    if sys.platform == "win32":
        junction = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(packages)],
            capture_output=True,
            check=False,
        )
        if junction.returncode == 0:
            return
    shutil.copytree(packages, link, symlinks=True)


def unlink_dependencies(target: Path) -> None:
    """Remove the links made by ``link_dependencies`` so that deleting ``target`` never reaches
    the installed packages."""
    for directory in project_directories(target):
        for name in DEPENDENCY_DIRS:
            link = directory / name
            if link.is_symlink():
                link.unlink()
            elif link.is_junction():
                os.rmdir(link)
