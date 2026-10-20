"""Gate 1 for the implementer: the tests the test author committed are not touched."""

from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass
from pathlib import Path

from forja.checks.base import rejected
from forja.checks.changes import ChangeKind, Changes
from forja.checks.scope import disposable, in_scope
from forja.core.gates import Approved, Finding, GateInput, GateResult
from forja.core.manifest import Manifest, ManifestEntry, build_manifest, manifest_of


def frozen_digest_of(worktree: Path, root: str, files: Collection[str]) -> str:
    """The digest of every file under ``root`` (when there is one), a tool's cache left out, and of
    the listed test files.

    Hidden files under ``root`` count: the build and the tests see what git ignores. A missing
    directory has the digest of an empty one, so deleting the whole directory is a change too.
    ``files`` are the tracked files the language adapters class as tests or fixtures; they sit
    beside the code in Go, JS/TS, C# and Java, where no directory holds the tests.
    """
    entries: dict[str, ManifestEntry] = {}
    if root:
        entries.update(_under_root(worktree, root))
    entries.update(manifest_of(worktree, files).entries)
    return Manifest(entries).digest()


def _under_root(worktree: Path, root: str) -> Mapping[str, ManifestEntry]:
    base = worktree / root
    if not base.is_dir():
        return {}
    return {
        f"{root}/{path}": ManifestEntry(f"{root}/{path}", e.kind, e.sha256, e.executable)
        for path, e in build_manifest(base).entries.items()
        if not disposable(f"{root}/{path}")
    }


def _is_frozen(path: str, root: str, is_test: Callable[[str], bool]) -> bool:
    return (bool(root) and in_scope(path, (root,))) or is_test(path)


@dataclass(frozen=True)
class FreezeCheck:
    """The tests the test author committed, under ``root`` or classed as tests by the language
    adapters, are what the implementer must leave as they are."""

    worktree: Path
    changes: Changes
    root: str
    digest: str
    tests: Collection[str] = ()  # the test files the worktree holds now
    is_test: Callable[[str], bool] = lambda path: False
    id: str = "freeze"
    gate: int = 1
    requires: frozenset[str] = frozenset()

    async def evaluate(self, data: GateInput) -> GateResult:
        if frozen_digest_of(self.worktree, self.root, self.tests) == self.digest:
            return Approved()
        touched = sorted(
            {
                path
                for change in self.changes.files
                for path in (change.old_path, change.path)
                if path is not None and _is_frozen(path, self.root, self.is_test)
            }
            | {path for path in self.changes.ignored if _is_frozen(path, self.root, self.is_test)}
        )
        findings = [Finding(message="a frozen test file was changed", target=p) for p in touched]
        return rejected(
            findings
            or [Finding(message="the frozen tests were changed", target=self.root or "tests")]
        )


@dataclass(frozen=True)
class AppendOnlyCheck:
    """An extra test stage may add test files but not change, move or delete one that already
    exists: the first test author, or an earlier extra stage, froze it."""

    changes: Changes
    root: str
    is_test: Callable[[str], bool] = lambda path: False
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
                if path is not None and _is_frozen(path, self.root, self.is_test)
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
