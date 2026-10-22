"""Where the projects of a repository are: every directory holding a language's manifest."""

import os
from collections.abc import Iterator, Sequence
from dataclasses import replace
from pathlib import Path

from forja.core.adapters.language import Detection, LanguageAdapter
from forja.core.adapters.scoped import ScopedAdapter

# Dependencies, build output and tool state: manifests in there are not the repository's own.
IGNORED_DIRECTORIES = frozenset({"node_modules", ".git", "target", "vendor", "bin", "obj"})


def project_directories(root: Path) -> Iterator[Path]:
    """``root`` first, then every directory below it in sorted order, skipping the ignored ones
    and the hidden ones."""
    for current, names, _ in os.walk(root):
        names[:] = sorted(n for n in names if n not in IGNORED_DIRECTORIES and n[0] != ".")
        yield Path(current)


def find_projects(adapter: LanguageAdapter, root: Path) -> list[Detection]:
    """One detection per directory under ``root`` where the adapter finds its manifest, with
    ``roots`` holding that directory relative to ``root`` (POSIX, ``.`` for ``root`` itself)."""
    found = []
    for directory in project_directories(root):
        detection = adapter.detect(directory)
        if detection is not None:
            where = directory.relative_to(root).as_posix()
            found.append(replace(detection, roots=(where,)))
    return found


def owner_of(projects: Sequence[ScopedAdapter], path: str) -> ScopedAdapter | None:
    """The project a file belongs to: among those whose directory holds it and whose adapter
    claims it, the deepest directory; a tie goes to the first in ``projects``. ``None`` when no
    project does."""
    claimed = [p for p in projects if p.classify(path) is not None]
    return max(claimed, key=lambda p: p.base.count("/") + (p.base != "."), default=None)
