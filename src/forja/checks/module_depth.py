"""Gate 8, opposing meter: a module should hide more than it shows.

Depth is the ratio of the public surface (one per public name plus one per parameter) to the
implementation (statements). A ratio above the limit means the module is shallow: its interface
costs the reader about as much as the code behind it. Only a module that is new or got shallower
reproves, and tiny modules are left alone. The readers live in ``structure``.
"""

import asyncio
from dataclasses import dataclass
from pathlib import Path

from forja.checks.base import rejected
from forja.checks.changes import Changes
from forja.checks.complexity import origin
from forja.checks.shape import language_of, read_texts, shapes, shapes_before, threshold, unreadable
from forja.checks.structure import SyntaxProblem
from forja.core.gates import Approved, Finding, GateInput, GateResult

DEFAULT_MAX_RATIO = 1.0  # a guess until the calibration of step 9
DEFAULT_MIN_STATEMENTS = 10


@dataclass(frozen=True)
class ModuleDepthCheck:
    worktree: Path
    changes: Changes
    files: tuple[str, ...]  # production files the attempt changed
    before: dict[str, str]  # the parent commit's text of those files, by old path
    id: str = "module_depth"
    gate: int = 8
    requires: frozenset[str] = frozenset({"structural_meters"})

    async def evaluate(self, data: GateInput) -> GateResult:
        return await asyncio.to_thread(self._judge, data)

    def _judge(self, data: GateInput) -> GateResult:
        if not self.files:
            return Approved()
        try:
            after = shapes(read_texts(self.worktree, self.files))
        except SyntaxProblem as problem:
            return unreadable(problem)
        was = shapes_before(self.before)
        findings = []
        for path, module in sorted(after.items()):
            language = language_of(path)
            limit = threshold(data, language, "max_interface_ratio", DEFAULT_MAX_RATIO)
            least = threshold(data, language, "min_statements", DEFAULT_MIN_STATEMENTS)
            if module.statements < least or module.ratio <= limit:
                continue
            old = was.get(origin(self.changes, path))
            if old is None or module.ratio > old.ratio:
                message = "module shows about as much as it hides"
                findings.append(
                    Finding(
                        message=message, target=path, measured=round(module.ratio, 2), limit=limit
                    )
                )
        return rejected(findings) if findings else Approved()
