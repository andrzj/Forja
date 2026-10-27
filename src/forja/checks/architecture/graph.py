"""The dependency graph between the directories of one project, and Martin's package metrics.

A node is the directory of a production file; an edge says some file in one directory imports a
file or package that lives in another. Nothing here looks at tests, fixtures or documents: the
caller hands over production files only.
"""

import posixpath
from collections import defaultdict
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

from forja.checks.architecture import csharp, go, java, script
from forja.checks.architecture import python as python_resolver
from forja.checks.architecture.facts import FileFacts, read_file
from forja.checks.structure import SyntaxProblem


class Unavailable(Exception):
    """The graph cannot be built: there is nothing to read, or ``go.mod`` names no module."""


@dataclass(frozen=True)
class PackageMetrics:
    afferent: int  # Ca: the directories that import this one
    efferent: int  # Ce: the directories this one imports
    instability: float  # I = Ce / (Ca + Ce), 0 when it has no edges
    abstractness: float  # A = abstract types / types, 0 when it has no types
    distance: float  # D = |A + I - 1|, from the main sequence
    types: int


@dataclass(frozen=True)
class Graph:
    nodes: frozenset[str]
    edges: frozenset[tuple[str, str]]  # (importer, imported), never from a directory to itself
    types: Mapping[str, tuple[int, int]] = field(default_factory=dict)  # abstract, all
    unreadable: tuple[str, ...] = ()  # files that do not parse and stay out of the graph

    def metrics(self, folder: str) -> PackageMetrics:
        afferent = sum(1 for _, imported in self.edges if imported == folder)
        efferent = sum(1 for importer, _ in self.edges if importer == folder)
        counts = self.types.get(folder)
        total = counts[1] if counts else 0
        instability = efferent / (afferent + efferent) if afferent + efferent else 0.0
        abstractness = counts[0] / max(counts[1], 1) if counts else 0.0
        distance = abs(abstractness + instability - 1)
        return PackageMetrics(afferent, efferent, instability, abstractness, distance, total)

    def cycles(self) -> tuple[frozenset[str], ...]:
        """The groups of directories that depend on each other, directly or through others."""
        return _components(self.nodes, self.edges)

    def path_in(self, group: frozenset[str], through: frozenset[str] = frozenset()) -> list[str]:
        """One cycle through the directories of ``group``, the first one repeated at the end.

        It starts at the first of ``through`` that ``group`` holds, if any.
        """
        inside: dict[str, list[str]] = defaultdict(list)
        for importer, imported in sorted(self.edges):
            if importer in group and imported in group:
                inside[importer].append(imported)
        start = min(group & through or group)
        seen = {start}
        queue: list[list[str]] = [[start]]
        while queue:
            path = queue.pop(0)
            for nxt in inside[path[-1]]:
                if nxt == start:
                    return [*path, start]
                if nxt not in seen:
                    seen.add(nxt)
                    queue.append([*path, nxt])
        return sorted(group)  # not reached for a real component


_Resolve = Callable[[Mapping[str, FileFacts]], set[tuple[str, str]]]
_RESOLVERS: dict[str, _Resolve] = {
    "python": python_resolver.resolve,
    "java": java.resolve,
    "csharp": csharp.resolve,
    "javascript": script.resolve,
    "typescript": script.resolve,
}


def build(language: str, files: Mapping[str, str], go_mod: str | None = None) -> Graph:
    """The graph of ``files`` (path inside the project, text), read as ``language``.

    Raises ``Unavailable`` when there is nothing to read, or for Go when ``go_mod`` is missing or
    names no module.
    """
    facts: dict[str, FileFacts] = {}
    unreadable: list[str] = []
    for path in sorted(files):
        try:
            found = read_file(path, files[path])
        except SyntaxProblem:
            unreadable.append(path)
            continue
        if found is not None:
            facts[path] = found
    if not facts:
        raise Unavailable("no file of the project could be read")
    if language == "go":
        module = go.module_path(go_mod or "")
        if module is None:
            raise Unavailable("go.mod names no module")
        edges = go.resolve(facts, module)
    else:
        edges = _RESOLVERS[language](facts)
    types: dict[str, tuple[int, int]] = {}
    for path, found in facts.items():
        folder = posixpath.dirname(path) or "."
        abstract, total = types.get(folder, (0, 0))
        types[folder] = (abstract + found.abstract, total + found.types)
    return Graph(
        frozenset(types),
        frozenset((a, b) for a, b in edges if a != b),
        types,
        tuple(unreadable),
    )


def _components(
    nodes: frozenset[str], edges: frozenset[tuple[str, str]]
) -> tuple[frozenset[str], ...]:
    """The strongly connected components with more than one node (Tarjan, without recursion)."""
    after: dict[str, list[str]] = defaultdict(list)
    for importer, imported in sorted(edges):
        after[importer].append(imported)
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    found: list[frozenset[str]] = []
    for root in sorted(nodes):
        if root in index:
            continue
        work: list[tuple[str, int]] = [(root, 0)]
        while work:
            node, at = work.pop()
            if at == 0:
                index[node] = low[node] = len(index)
                stack.append(node)
                on_stack.add(node)
            children = after[node]
            if at < len(children):
                work.append((node, at + 1))
                child = children[at]
                if child not in index:
                    work.append((child, 0))
                elif child in on_stack:
                    low[node] = min(low[node], index[child])
                continue
            if low[node] == index[node]:
                group = []
                while True:
                    member = stack.pop()
                    on_stack.discard(member)
                    group.append(member)
                    if member == node:
                        break
                if len(group) > 1:
                    found.append(frozenset(group))
            if work:
                parent = work[-1][0]
                low[parent] = min(low[parent], low[node])
    return tuple(sorted(found, key=sorted))
