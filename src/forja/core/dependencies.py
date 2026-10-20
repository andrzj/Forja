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

DEPENDENCY_DIRS = ("node_modules",)


class _Git(Protocol):
    async def lines(self, *args: str) -> list[str]: ...


async def stage_all(git: _Git) -> None:
    """Stage everything in the worktree but the dependencies: a link that git does not ignore
    would otherwise be added (an exclude pathspec makes git fail when the path is ignored)."""
    await git.lines("add", "-A")
    await git.lines("reset", "-q", "--", *DEPENDENCY_DIRS)


def is_dependency(path: str) -> bool:
    """Whether ``path`` is one of the dependency directories or lies under one."""
    return path.replace("\\", "/").split("/")[0] in DEPENDENCY_DIRS


def link_dependencies(source: Path, target: Path) -> None:
    """Let ``target`` use the dependencies installed in ``source`` without copying them: a link,
    a junction where Windows allows no link, a copy as the last resort."""
    for name in DEPENDENCY_DIRS:
        packages = source / name
        if not packages.is_dir():
            continue
        link = target / name
        try:
            os.symlink(packages, link, target_is_directory=True)
            continue
        except OSError:
            pass
        if sys.platform == "win32":
            junction = subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(link), str(packages)],
                capture_output=True,
                check=False,
            )
            if junction.returncode == 0:
                continue
        shutil.copytree(packages, link, symlinks=True)


def unlink_dependencies(target: Path) -> None:
    """Remove the links made by ``link_dependencies`` so that deleting ``target`` never reaches
    the installed packages."""
    for name in DEPENDENCY_DIRS:
        link = target / name
        if link.is_symlink():
            link.unlink()
        elif link.is_junction():
            os.rmdir(link)
