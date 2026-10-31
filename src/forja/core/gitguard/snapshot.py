"""A fingerprint of everything an agent could change in git, taken before and after each call.

The agent works in a copy with no `.git`, so any difference means it reached the real repository.
The snapshot is semantic where git refreshes bytes on its own (the index is read through
`ls-files --stage`), so merely running `git status` is not a change.
"""

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from types import TracebackType
from typing import Self

from forja.core.idempotency.git import Git


class DifferenceKind(StrEnum):
    REF_ADDED = "ref_added"
    REF_REMOVED = "ref_removed"
    REF_MOVED = "ref_moved"
    WORKTREE_ADDED = "worktree_added"
    WORKTREE_REMOVED = "worktree_removed"
    HEAD_CHANGED = "head_changed"
    BRANCH_CHANGED = "branch_changed"
    INDEX_CHANGED = "index_changed"
    CONFIG_CHANGED = "config_changed"
    HOOKS_CHANGED = "hooks_changed"


@dataclass(frozen=True)
class Difference:
    kind: DifferenceKind
    subject: str
    before: str | None = None
    after: str | None = None

    def describe(self) -> str:
        change = (
            "" if self.before is None and self.after is None else f": {self.before} -> {self.after}"
        )
        return f"{self.kind.value} {self.subject}{change}"


@dataclass(frozen=True)
class WorktreeState:
    head: str | None
    branch: str | None
    index: str  # digest of `ls-files --stage`, or "absent"


@dataclass(frozen=True)
class GitSnapshot:
    worktrees: dict[str, WorktreeState]  # by path, as git reports it
    refs: dict[str, str]  # full ref name -> object id, packed and loose, stash and tags included
    config: str
    hooks: str


def _digest(lines: list[str]) -> str:
    return hashlib.sha256("\n".join(lines).encode("utf-8", errors="surrogateescape")).hexdigest()


def _file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else "absent"


async def take_snapshot(git: Git) -> GitSnapshot:
    """Fingerprint the repository ``git`` points to, with its shared refs and every worktree."""
    worktrees: dict[str, WorktreeState] = {}
    path: str | None = None
    head: str | None = None
    branch: str | None = None

    async def close_block() -> None:
        if path is not None:
            index = "absent"
            if Path(path).is_dir():
                staged = await git.at(Path(path)).lines("ls-files", "--stage")
                index = _digest(staged)
            worktrees[path] = WorktreeState(head, branch, index)

    for line in [*await git.lines("worktree", "list", "--porcelain"), ""]:
        if line.startswith("worktree "):
            path, head, branch = line.removeprefix("worktree "), None, None
        elif line.startswith("HEAD "):
            head = line.removeprefix("HEAD ")
        elif line.startswith("branch "):
            branch = line.removeprefix("branch ")
        elif line == "":
            await close_block()
            path = None

    refs: dict[str, str] = {}
    for line in await git.lines("for-each-ref", "--format=%(refname) %(objectname)"):
        name, _, object_id = line.rpartition(" ")
        refs[name] = object_id

    (common,) = await git.lines("rev-parse", "--git-common-dir")
    common_dir = (git.repo / common).resolve()
    hooks_dir = common_dir / "hooks"
    hook_lines = (
        sorted(f"{p.name} {_file_digest(p)}" for p in hooks_dir.iterdir() if p.is_file())
        if hooks_dir.is_dir()
        else []
    )
    return GitSnapshot(worktrees, refs, _file_digest(common_dir / "config"), _digest(hook_lines))


def compare_snapshots(before: GitSnapshot, after: GitSnapshot) -> list[Difference]:
    """Every difference between two snapshots; an empty list means git was left untouched."""
    found: list[Difference] = []
    for name in sorted(before.refs.keys() | after.refs.keys()):
        old, new = before.refs.get(name), after.refs.get(name)
        if old is None:
            found.append(Difference(DifferenceKind.REF_ADDED, name, None, new))
        elif new is None:
            found.append(Difference(DifferenceKind.REF_REMOVED, name, old, None))
        elif old != new:
            found.append(Difference(DifferenceKind.REF_MOVED, name, old, new))

    for path in sorted(before.worktrees.keys() | after.worktrees.keys()):
        old_wt, new_wt = before.worktrees.get(path), after.worktrees.get(path)
        if old_wt is None:
            found.append(Difference(DifferenceKind.WORKTREE_ADDED, path))
        elif new_wt is None:
            found.append(Difference(DifferenceKind.WORKTREE_REMOVED, path))
        else:
            for kind, a, b in (
                (DifferenceKind.HEAD_CHANGED, old_wt.head, new_wt.head),
                (DifferenceKind.BRANCH_CHANGED, old_wt.branch, new_wt.branch),
                (DifferenceKind.INDEX_CHANGED, old_wt.index, new_wt.index),
            ):
                if a != b:
                    found.append(Difference(kind, path, a, b))

    if before.config != after.config:
        found.append(Difference(DifferenceKind.CONFIG_CHANGED, "config"))
    if before.hooks != after.hooks:
        found.append(Difference(DifferenceKind.HOOKS_CHANGED, "hooks"))
    return found


class GitWatch:
    """Take a snapshot on entry and another on exit; ``differences`` holds what changed.

    It never raises on a difference: the caller turns it into a rejection of the attempt. An
    exception raised inside the block propagates, and the comparison is still made.
    Forja must not change what it watches while the block runs, except what ``ignore`` names: with
    tasks running together, the work Forja does for the others is not the agent's.
    """

    def __init__(self, git: Git, ignore: Callable[[Difference], bool] | None = None) -> None:
        self._git = git
        self._ignore = ignore
        self.before: GitSnapshot | None = None
        self.after: GitSnapshot | None = None
        self.differences: list[Difference] = []

    async def __aenter__(self) -> Self:
        self.before = await take_snapshot(self._git)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        assert self.before is not None
        self.after = await take_snapshot(self._git)
        found = compare_snapshots(self.before, self.after)
        self.differences = [d for d in found if self._ignore is None or not self._ignore(d)]
