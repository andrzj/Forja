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

_CHUNK = 1 << 20
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
    _scan(root, "", frozenset(exclude), entries)
    return Manifest(entries)


def _scan(
    directory: Path, prefix: str, exclude: frozenset[str], out: dict[str, ManifestEntry]
) -> None:
    with os.scandir(directory) as scan:
        children = sorted(scan, key=lambda child: child.name)
    for child in children:
        if not prefix and child.name in exclude:
            continue
        relative = f"{prefix}{child.name}"
        if child.is_symlink():
            target = os.readlink(child.path)
            digest = hashlib.sha256(target.encode("utf-8", errors="surrogateescape")).hexdigest()
            out[relative] = ManifestEntry(relative, EntryKind.SYMLINK, digest, False)
        elif child.is_dir(follow_symlinks=False):
            _scan(Path(child.path), f"{relative}/", exclude, out)
        elif child.is_file(follow_symlinks=False):
            out[relative] = ManifestEntry(
                relative, EntryKind.FILE, _hash_file(child.path), _is_executable(child)
            )


def _hash_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while chunk := handle.read(_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def _is_executable(entry: os.DirEntry[str]) -> bool:
    if sys.platform == "win32":
        return False
    return bool(entry.stat(follow_symlinks=False).st_mode & stat.S_IXUSR)


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
