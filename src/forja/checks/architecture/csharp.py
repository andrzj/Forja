"""C#: a ``using`` names a namespace, matched with the namespaces the files declare."""

import posixpath
from collections import defaultdict
from collections.abc import Mapping

from forja.checks.architecture.facts import FileFacts


def resolve(facts: Mapping[str, FileFacts]) -> set[tuple[str, str]]:
    namespaces: dict[str, set[str]] = defaultdict(set)
    for path, found in facts.items():
        for name in found.declared:
            namespaces[name].add(posixpath.dirname(path) or ".")
    edges: set[tuple[str, str]] = set()
    for path, found in facts.items():
        source = posixpath.dirname(path) or "."
        for target in found.imports:
            parts = target.split(".")
            for size in range(len(parts), 0, -1):
                hit = namespaces.get(".".join(parts[:size]))
                if hit:  # a type, a static class or an alias names a namespace by its prefix
                    edges.update((source, folder) for folder in hit)
                    break
    return edges
