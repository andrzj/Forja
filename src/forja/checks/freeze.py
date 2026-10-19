"""Gate 1 for the implementer: the tests the test author committed are not touched."""

from dataclasses import dataclass
from pathlib import Path

from forja.checks.base import rejected
from forja.checks.changes import ChangeKind, Changes
from forja.checks.scope import disposable, in_scope
from forja.core.gates import Approved, Finding, GateInput, GateResult
from forja.core.manifest import Manifest, build_manifest


def tree_digest(worktree: Path, root: str) -> str:
    """The digest of every file under ``root``, a tool's cache left out.

    Hidden files count: the build and the tests see what git ignores. A missing directory has the
    digest of an empty one, so deleting the whole directory is a change too.
    """
    base = worktree / root
    entries = (
        {
            path: entry
            for path, entry in build_manifest(base).entries.items()
            if not disposable(f"{root}/{path}")
        }
        if base.is_dir()
        else {}
    )
    return Manifest(entries).digest()


@dataclass(frozen=True)
class FreezeCheck:
    """What the test author committed under ``root`` is what the implementer must leave there."""

    worktree: Path
    changes: Changes
    root: str
    digest: str
    id: str = "freeze"
    gate: int = 1
    requires: frozenset[str] = frozenset()

    async def evaluate(self, data: GateInput) -> GateResult:
        if tree_digest(self.worktree, self.root) == self.digest:
            return Approved()
        touched = sorted(
            {
                path
                for change in self.changes.files
                for path in (change.old_path, change.path)
                if path is not None and in_scope(path, (self.root,))
            }
            | {path for path in self.changes.ignored if in_scope(path, (self.root,))}
        )
        findings = [Finding(message="a frozen test file was changed", target=p) for p in touched]
        return rejected(
            findings or [Finding(message="the frozen tests were changed", target=self.root)]
        )


@dataclass(frozen=True)
class AppendOnlyCheck:
    """An extra test stage may add test files under ``root`` but not change, move or delete one
    that already exists: the first test author, or an earlier extra stage, froze it."""

    changes: Changes
    root: str
    id: str = "freeze"
    gate: int = 1
    requires: frozenset[str] = frozenset()

    async def evaluate(self, data: GateInput) -> GateResult:
        touched = sorted(
            {
                path
                for change in self.changes.files
                if change.kind is not ChangeKind.ADDED
                for path in (change.old_path, change.path)
                if path is not None and in_scope(path, (self.root,))
            }
        )
        if not touched:
            return Approved()
        return rejected(
            [
                Finding(message="a test file that already existed was changed", target=p)
                for p in touched
            ]
        )
