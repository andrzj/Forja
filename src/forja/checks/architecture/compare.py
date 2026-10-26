"""What the three architecture checks share: the graph before and after an attempt.

The caller hands over the production files of one project in the parent commit and in the
attempt, so no check copies a worktree. A check that cannot say anything gets its answer here.
"""

from collections.abc import Mapping
from dataclasses import dataclass

from forja.checks.architecture.graph import Graph, Unavailable, build
from forja.checks.structure import dialect_of
from forja.core.gates import Approved, GateResult, Inconclusive
from forja.core.gates.models import InconclusiveReason


@dataclass(frozen=True)
class Snapshot:
    """The production files of one project in one state of the repository."""

    language: str
    files: Mapping[str, str]  # path inside the project -> text
    go_mod: str | None = None  # the text of ``go.mod``, for Go


@dataclass(frozen=True)
class Compared:
    before: Graph | None  # ``None`` when the parent commit has nothing to compare with
    after: Graph
    touched: frozenset[str]  # the directories of the production files the attempt changed


def compare(before: Snapshot, after: Snapshot, changed: tuple[str, ...]) -> Compared | GateResult:
    """Both graphs, or the answer when there is nothing to judge or the files cannot be read.

    ``changed`` are the production files the attempt added, changed or renamed. A change to a
    file in a language Forja does not read, or only deletions, leaves the graph as it was.
    """
    touched = tuple(p for p in changed if p in after.files and dialect_of(p) is not None)
    if not touched:
        return Approved()
    try:
        graph = build(after.language, after.files, after.go_mod)
    except Unavailable as problem:
        return Inconclusive(reason=InconclusiveReason.UNSUPPORTED_CONSTRUCT, detail=str(problem))
    broken = sorted(set(touched) & set(graph.unreadable))
    if broken:
        detail = f"{', '.join(broken)} does not parse, so its imports cannot be read"
        return Inconclusive(reason=InconclusiveReason.UNSUPPORTED_CONSTRUCT, detail=detail)
    try:
        old: Graph | None = build(before.language, before.files, before.go_mod)
    except Unavailable:
        old = None
    return Compared(old, graph, frozenset(_folder(p) for p in touched))


def _folder(path: str) -> str:
    head, _, _ = path.rpartition("/")
    return head or "."
