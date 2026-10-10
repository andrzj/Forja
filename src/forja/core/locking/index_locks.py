"""Remove the `index.lock` a killed git command left behind, and only when that is safe."""

import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from forja.core.idempotency.git import Git
from forja.core.process import running_process_names

_GIT_NAMES = frozenset({"git", "git.exe"})


@dataclass(frozen=True)
class IndexLockReport:
    removed: tuple[Path, ...]
    kept: tuple[tuple[Path, str], ...]  # path and why it was left alone


def git_is_running() -> bool:
    return bool(_GIT_NAMES & running_process_names())


async def remove_orphan_index_locks(
    git: Git,
    *,
    min_age: float = 60.0,
    git_running: Callable[[], bool] = git_is_running,
    now: Callable[[], float] = time.time,
) -> IndexLockReport:
    """Delete stale ``index.lock`` files of the repository and of each of its worktrees.

    A lock is removed only if it is at least ``min_age`` seconds old *and* no git process runs on
    the machine. Anything else could be a live command, so it is kept and reported. Call it while
    holding the repository lock and the git mutex, before work resumes.
    """
    (common,) = await git.lines("rev-parse", "--git-common-dir")
    common_dir = (git.repo / common).resolve()
    candidates = [common_dir / "index.lock"]
    worktrees = common_dir / "worktrees"
    if worktrees.is_dir():
        candidates.extend(sorted(worktrees.glob("*/index.lock")))
    present = [path for path in candidates if path.is_file()]

    removed: list[Path] = []
    kept: list[tuple[Path, str]] = []
    running = git_running() if present else False
    for path in present:
        age = now() - path.stat().st_mtime
        if age < min_age:
            kept.append((path, f"only {age:.0f} s old; a git command may still be running"))
        elif running:
            kept.append((path, "a git process is running"))
        else:
            try:
                path.unlink()
            except OSError as error:
                kept.append((path, f"could not be removed: {error}"))
            else:
                removed.append(path)
    return IndexLockReport(tuple(removed), tuple(kept))
