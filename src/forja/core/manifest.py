"""Manifest of a working copy: what the agent changed is the difference between two manifests.

Applying a change means taking the target tree to the expected manifest, which can be verified
and repeated safely (contract 2, transfer between working copy and worktree).
"""

import hashlib
import json
import os
import stat
import sys
from collections import defaultdict
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

# Windows file systems have no execute bit; kept as a name so a test can stand in for either side.
_HAS_EXECUTE_BIT = sys.platform != "win32"
# Usable characters of a classic Windows path (MAX_PATH is 260 including the terminator).
WINDOWS_MAX_PATH = 259


class EntryKind(StrEnum):
    FILE = "file"
    SYMLINK = "symlink"


@dataclass(frozen=True)
class ManifestEntry:
    """``sha256`` is of the content bytes, or of the link target for a symlink.

    ``executable`` is always false on Windows, whose file system has no such bit; git records
    it separately.
    """

    path: str
    kind: EntryKind
    sha256: str
    executable: bool


@dataclass(frozen=True)
class Manifest:
    entries: Mapping[str, ManifestEntry]

    def digest(self) -> str:
        """SHA-256 of a canonical form: entries sorted by path, compact JSON."""
        rows = [
            [e.path, e.kind.value, e.sha256, e.executable] for _, e in sorted(self.entries.items())
        ]
        # The rows are lists, so only the item separator is ever used, and ensure_ascii is the
        # default; both are spelled out so the canonical form is readable here.
        payload = json.dumps(rows, separators=(",", ":"), ensure_ascii=True)
        return hashlib.sha256(payload.encode("ascii")).hexdigest()


@dataclass(frozen=True)
class ManifestDiff:
    created: tuple[str, ...]
    modified: tuple[str, ...]
    removed: tuple[str, ...]

    @property
    def is_empty(self) -> bool:
        return not (self.created or self.modified or self.removed)


class ViolationKind(StrEnum):
    SYMLINK = "symlink"
    CASE_COLLISION = "case_collision"
    PATH_TOO_LONG = "path_too_long"


@dataclass(frozen=True)
class Violation:
    kind: ViolationKind
    path: str
    detail: str


def build_manifest(root: Path, *, exclude: Collection[str] = ()) -> Manifest:
    """Manifest of every file and symlink under ``root``; empty directories are ignored.

    ``exclude`` lists names skipped at the top level only (for example ``.git`` in a worktree).
    Symlinks are recorded, never followed. Content is hashed as raw bytes: line endings are
    not normalized.
    """
    entries: dict[str, ManifestEntry] = {}
    _scan(root, "", exclude, entries)
    return Manifest(entries)


def _scan(
    directory: Path, prefix: str, skip: Collection[str], out: dict[str, ManifestEntry]
) -> None:
    with os.scandir(directory) as scan:
        children = sorted(scan, key=lambda child: child.name)
    for child in children:
        if child.name in skip:
            continue
        relative = f"{prefix}{child.name}"
        if child.is_symlink() or child.is_junction():  # a junction leads out like a link does
            target = os.readlink(child.path)
            digest = hashlib.sha256(os.fsencode(target)).hexdigest()
            out[relative] = ManifestEntry(relative, EntryKind.SYMLINK, digest, False)
        elif child.is_dir():
            _scan(Path(child.path), f"{relative}/", (), out)
        elif child.is_file():
            out[relative] = ManifestEntry(
                relative, EntryKind.FILE, _hash_file(child.path), _is_executable(child)
            )


def manifest_of(root: Path, paths: Collection[str]) -> Manifest:
    """Manifest of the listed regular files under ``root``; any other path is left out."""
    entries: dict[str, ManifestEntry] = {}
    for relative in paths:
        path = root / relative
        if path.is_file() and not path.is_symlink():
            entries[relative] = ManifestEntry(
                relative, EntryKind.FILE, _hash_file(str(path)), _executable_bit(path)
            )
    return Manifest(entries)


def _hash_file(path: str) -> str:
    with open(path, "rb") as handle:
        return hashlib.file_digest(handle, hashlib.sha256).hexdigest()


def _is_executable(entry: os.DirEntry[str]) -> bool:
    return _HAS_EXECUTE_BIT and bool(entry.stat().st_mode & stat.S_IXUSR)


def _executable_bit(path: Path) -> bool:
    return _HAS_EXECUTE_BIT and bool(path.stat().st_mode & stat.S_IXUSR)


def diff_manifests(before: Manifest, after: Manifest) -> ManifestDiff:
    """What changed from ``before`` to ``after``. A rename shows as a removal plus a creation."""
    created = sorted(set(after.entries) - set(before.entries))
    removed = sorted(set(before.entries) - set(after.entries))
    modified = sorted(
        path
        for path in set(before.entries) & set(after.entries)
        if before.entries[path] != after.entries[path]
    )
    return ManifestDiff(tuple(created), tuple(modified), tuple(removed))


def find_violations(
    manifest: Manifest, *, destination_root: Path, max_path_length: int = WINDOWS_MAX_PATH
) -> list[Violation]:
    """Changes the destination cannot represent faithfully; any one rejects the attempt."""
    violations: list[Violation] = []
    by_folded_name: defaultdict[str, list[str]] = defaultdict(list)
    for path, entry in sorted(manifest.entries.items()):
        by_folded_name[path.casefold()].append(path)
        if entry.kind is EntryKind.SYMLINK:
            violations.append(
                Violation(ViolationKind.SYMLINK, path, "symlink may point outside the working copy")
            )
        full_length = len(str(destination_root)) + 1 + len(path)
        if full_length > max_path_length:
            violations.append(
                Violation(
                    ViolationKind.PATH_TOO_LONG,
                    path,
                    f"{full_length} characters under the destination exceeds {max_path_length}",
                )
            )
    for paths in by_folded_name.values():
        if len(paths) > 1:
            for path in paths:
                violations.append(
                    Violation(
                        ViolationKind.CASE_COLLISION,
                        path,
                        f"differs only by case from: {', '.join(p for p in paths if p != path)}",
                    )
                )
    return violations
