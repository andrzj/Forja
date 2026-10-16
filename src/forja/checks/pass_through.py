"""Gate 8, opposing meter: lowering complexity must not leave functions that only pass work on.

A function whose whole body calls another with its own parameters, unchanged and in order, adds a
name and a hop and nothing else. As with complexity, only a function that is new or became one
reproves; old ones are debt for the planner. Wrappers that carry logic of their own (decorators in
Python) and the dunder methods of Python are not counted. The readers live in ``structure``.
"""

import asyncio
from dataclasses import dataclass
from pathlib import Path

from forja.checks.base import rejected
from forja.checks.changes import Changes
from forja.checks.complexity import origin
from forja.checks.shape import read_texts, shapes, shapes_before, unreadable
from forja.checks.structure import SyntaxProblem
from forja.core.gates import Approved, Finding, GateInput, GateResult


@dataclass(frozen=True)
class PassThroughCheck:
    worktree: Path
    changes: Changes
    files: tuple[str, ...]  # production files the attempt changed
    before: dict[str, str]  # the parent commit's text of those files, by old path
    id: str = "pass_through"
    gate: int = 8
    requires: frozenset[str] = frozenset({"structural_meters"})

    async def evaluate(self, data: GateInput) -> GateResult:
        return await asyncio.to_thread(self._judge)

    def _judge(self) -> GateResult:
        if not self.files:
            return Approved()
        try:
            after = shapes(read_texts(self.worktree, self.files))
        except SyntaxProblem as problem:
            return unreadable(problem)
        was = shapes_before(self.before)
        findings = []
        for path, module in sorted(after.items()):
            old = was.get(origin(self.changes, path))
            known = old.forwarders if old is not None else frozenset()
            for name in sorted(module.forwarders - known):
                message = f"function {name} only passes its arguments on"
                findings.append(Finding(message=message, target=f"{path}::{name}"))
        return rejected(findings) if findings else Approved()
