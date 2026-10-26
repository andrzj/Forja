"""Gate 9: an attempt must not create a dependency cycle between directories.

A cycle is a group of directories that import each other, directly or through others. Only a
cycle that is new reproves, or an old one that took in one more directory: a cycle that stays as
it was, or shrinks, is the repository's past and not the attempt's doing. Go refuses a cycle of
packages at compile time, so this check finds none there.
"""

import asyncio
from dataclasses import dataclass

from forja.checks.architecture.compare import Compared, Snapshot, compare
from forja.checks.base import rejected
from forja.core.gates import Approved, Finding, GateInput, GateResult


@dataclass(frozen=True)
class DependencyCyclesCheck:
    before: Snapshot  # the parent commit
    after: Snapshot  # the attempt
    changed: tuple[str, ...]  # production files the attempt added, changed or renamed
    id: str = "dependency_cycles"
    gate: int = 9
    requires: frozenset[str] = frozenset({"structural_meters"})

    async def evaluate(self, data: GateInput) -> GateResult:
        return await asyncio.to_thread(self._judge)

    def _judge(self) -> GateResult:
        found = compare(self.before, self.after, self.changed)
        if not isinstance(found, Compared):
            return found
        old = found.before.cycles() if found.before is not None else ()
        findings = []
        for group in found.after.cycles():
            if any(group <= was for was in old):
                continue
            grew = any(group & was for was in old)
            through = group - frozenset().union(*old) if grew else found.touched
            path = found.after.path_in(group, through)
            message = (
                "a dependency cycle took in more directories"
                if grew
                else "new dependency cycle between directories"
            )
            findings.append(
                Finding(message=message, target=" -> ".join(path), measured=len(group), limit=1)
            )
        return rejected(findings) if findings else Approved()
