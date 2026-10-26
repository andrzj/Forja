"""JavaScript and TypeScript: only a relative specifier names a file of the project.

A bare specifier is a package, and the ``paths`` of a ``tsconfig`` and the aliases of a bundler
are not resolved, so an import through one of them is not an edge.
"""

import posixpath
from collections.abc import Mapping

from forja.checks.architecture.facts import FileFacts

_SUFFIXES = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".mts", ".cts")
_COMPILED = {".js": (".ts", ".tsx"), ".jsx": (".tsx",), ".mjs": (".mts",), ".cjs": (".cts",)}


def resolve(facts: Mapping[str, FileFacts]) -> set[tuple[str, str]]:
    paths = set(facts)
    edges: set[tuple[str, str]] = set()
    for path, found in facts.items():
        folder = posixpath.dirname(path)
        for target in found.imports:
            if not target.startswith("."):
                continue
            hit = _find(posixpath.normpath(posixpath.join(folder, target)), paths)
            if hit is not None:
                edges.add((folder or ".", posixpath.dirname(hit) or "."))
    return edges


def _find(base: str, paths: set[str]) -> str | None:
    if base == ".." or base.startswith("../"):
        return None  # outside the project
    stem, suffix = posixpath.splitext(base)
    candidates = [base] if suffix in _SUFFIXES else []
    candidates += [stem + other for other in _COMPILED.get(suffix, ())]
    candidates += [base + s for s in _SUFFIXES]
    candidates += [posixpath.normpath(posixpath.join(base, f"index{s}")) for s in _SUFFIXES]
    return next((c for c in candidates if c in paths), None)
