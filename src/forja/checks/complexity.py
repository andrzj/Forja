"""Gate 8 (the part Forja has today): no function got more complex than the limit allows.

The tool is lizard, which reads many languages, so this check is not tied to one. The limit comes
from the policy per language. A function above it reproves only when it is new or got worse: old
complexity is debt for the planner, not a reason to refuse an unrelated improvement.
"""

import csv
import tempfile
from dataclasses import dataclass
from pathlib import Path

from forja.checks.base import Undecided, decided, rejected
from forja.checks.changes import Changes, write_files
from forja.checks.tooling import Tools
from forja.core.adapters import CommandPlan
from forja.core.gates import Approved, Finding, GateInput, GateResult, Inconclusive
from forja.core.gates.models import InconclusiveReason

DEFAULT_MAX_CCN = 15  # lizard's own default
FIELDS = 11  # NLOC, CCN, tokens, params, length, "name@lines@file", file, name, long name, from, to

Functions = dict[tuple[str, str], int]


def max_ccn(data: GateInput, language: str) -> int:
    thresholds = data.values.get("thresholds")
    per_language = thresholds.get(language) if isinstance(thresholds, dict) else None
    value = per_language.get("max_ccn") if isinstance(per_language, dict) else None
    return int(value) if isinstance(value, int | float) and value > 0 else DEFAULT_MAX_CCN


def parse_functions(lines: list[str]) -> Functions:
    """Complexity by (file, function). Methods with the same name keep the worst one."""
    found: Functions = {}
    for row in csv.reader(lines):
        if len(row) != FIELDS or not row[1].isdigit():
            continue
        key = (row[6].replace("\\", "/"), row[7])
        found[key] = max(found.get(key, 0), int(row[1]))
    return found


@dataclass(frozen=True)
class ComplexityCheck:
    tools: Tools
    worktree: Path
    changes: Changes
    files: tuple[str, ...]  # production files the attempt changed that lizard should read
    before: dict[str, str]  # the parent commit's text of those files, by old path
    lizard: tuple[str, ...]
    language: str = "python"
    id: str = "complexity"
    gate: int = 8
    requires: frozenset[str] = frozenset({"structural_meters"})

    async def evaluate(self, data: GateInput) -> GateResult:
        return await decided(self._judge(data))

    async def _judge(self, data: GateInput) -> GateResult:
        if not self.files:
            return Approved()
        limit = max_ccn(data, self.language)
        after = await self._read(self.worktree, self.files)
        was = await self._before()
        findings = []
        for (path, name), ccn in sorted(after.items()):
            old = was.get((self._origin(path), name))
            if ccn > limit and (old is None or ccn > old):
                message = f"function {name} is too complex"
                findings.append(
                    Finding(message=message, target=f"{path}::{name}", measured=ccn, limit=limit)
                )
        return rejected(findings) if findings else Approved()

    def _origin(self, path: str) -> str:
        for change in self.changes.files:
            if change.path == path:
                return change.before or path
        return path

    async def _before(self) -> Functions:
        if not self.before:
            return {}
        with tempfile.TemporaryDirectory(prefix="forja-before-") as directory:
            write_files(self.before, Path(directory))
            return await self._read(Path(directory), tuple(sorted(self.before)))

    async def _read(self, root: Path, files: tuple[str, ...]) -> Functions:
        plan = CommandPlan((*self.lizard, "--csv", "--", *files), root, env_set={"NO_COLOR": "1"})
        execution = await self.tools.run("complexity", plan)
        if not execution.finished:
            raise Undecided(execution.inconclusive("complexity"))
        if execution.result.exit_code != 0:
            detail = f"complexity: lizard ended with {execution.result.exit_code}"
            raise Undecided(
                Inconclusive(
                    reason=InconclusiveReason.TOOL_FAILED,
                    detail=detail,
                    tool_run_ids=(execution.operation_id,),
                )
            )
        return parse_functions(execution.lines)
