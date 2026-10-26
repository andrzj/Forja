"""Java: an import names a type or a package, matched with what the files declare."""

import posixpath
from collections import defaultdict
from collections.abc import Mapping

from forja.checks.architecture.facts import FileFacts


def resolve(facts: Mapping[str, FileFacts]) -> set[tuple[str, str]]:
    packages: dict[str, set[str]] = defaultdict(set)
    types: dict[str, set[str]] = defaultdict(set)
    for path, found in facts.items():
        if not found.declared:
            continue
        folder = posixpath.dirname(path) or "."
        packages[found.declared[0]].add(folder)
        for name in found.declared[1:]:
            types[name].add(folder)
    edges: set[tuple[str, str]] = set()
    for path, found in facts.items():
        source = posixpath.dirname(path) or "."
        for target in found.imports:
            for folder in _targets(target, packages, types):
                edges.add((source, folder))
    return edges


def _targets(
    target: str, packages: Mapping[str, set[str]], types: Mapping[str, set[str]]
) -> set[str]:
    name = target.removesuffix(".*")
    if target.endswith(".*") and name in packages:
        return set(packages[name])
    parts = name.split(".")
    for size in range(len(parts), 0, -1):
        hit = types.get(".".join(parts[:size]))
        if hit:
            return set(hit)
    return set()
