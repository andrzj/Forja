from collections.abc import Iterable
from dataclasses import dataclass

from forja.core.idempotency.git import Git

_FALLBACK = ("main", "master")


@dataclass(frozen=True)
class ProtectedBranches:
    """Branches Forja never writes to: the repository's default branch and any the user adds."""

    names: frozenset[str]

    def is_protected(self, branch: str) -> bool:
        return branch.removeprefix("refs/heads/") in self.names


async def detect_protected_branches(git: Git, extra: Iterable[str] = ()) -> ProtectedBranches:
    """Default branch from ``origin/HEAD``; ``main`` and ``master`` when it cannot be told."""
    names = set(extra)
    result = await git.run("symbolic-ref", "--short", "refs/remotes/origin/HEAD")
    if result.exit_code == 0 and result.lines and "/" in result.lines[0]:
        names.add(result.lines[0].split("/", 1)[1])
    else:
        names.update(_FALLBACK)
    return ProtectedBranches(frozenset(names))
