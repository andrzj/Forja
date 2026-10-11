"""Gate 2: gitleaks finds no secret in what the attempt added.

Only the added lines are scanned, so removing a secret never reproves an attempt. The secret
itself is never copied into a finding: the next attempt is told the rule and the place.
"""

import json
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from forja.checks.base import Undecided, decided, rejected
from forja.checks.changes import AddedLine, Changes, added_lines
from forja.checks.tooling import Tools
from forja.core.adapters import CommandPlan
from forja.core.atomic import atomic_write_bytes
from forja.core.gates import (
    Approved,
    Finding,
    GateInput,
    GateResult,
    Inconclusive,
    InconclusiveReason,
    Location,
)

LEAKS_FOUND = 2  # chosen with --exit-code: gitleaks uses 1 for leaks and for its own errors alike


@dataclass(frozen=True)
class SecretsCheck:
    tools: Tools
    worktree: Path
    changes: Changes
    reports: Path  # a directory outside the worktree for the scan input and report
    gitleaks: tuple[str, ...] = ("gitleaks",)
    id: str = "secrets"
    gate: int = 2
    requires: frozenset[str] = frozenset()

    async def evaluate(self, data: GateInput) -> GateResult:
        return await decided(self._judge())

    async def _judge(self) -> GateResult:
        added = added_lines(self.changes.patch)
        if not added:
            return Approved()
        self.reports.mkdir(parents=True, exist_ok=True)
        scanned, report = self.reports / "added.txt", self.reports / "gitleaks.json"
        atomic_write_bytes(scanned, "\n".join(line.text for line in added).encode("utf-8"))
        report.unlink(missing_ok=True)
        plan = CommandPlan(
            (
                *self.gitleaks,
                "stdin",
                "--no-banner",
                "--redact",
                "--exit-code",
                str(LEAKS_FOUND),
                "--report-format",
                "json",
                "--report-path",
                str(report),
            ),  # fmt: skip
            self.worktree,
            stdin_file=scanned,
        )
        execution = await self.tools.run("secrets", plan)
        if not execution.finished:
            raise Undecided(execution.inconclusive("secrets"))
        code = execution.result.exit_code
        if code == 0:
            return Approved()
        if code != LEAKS_FOUND:
            raise Undecided(
                Inconclusive(
                    reason=InconclusiveReason.TOOL_FAILED,
                    detail=f"secrets: gitleaks ended with {code}",
                    tool_run_ids=(execution.operation_id,),
                )
            )
        return rejected(self._findings(report, added))

    @staticmethod
    def _findings(report: Path, added: list[AddedLine]) -> list[Finding]:
        try:
            leaks = json.loads(report.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            leaks = []
        findings = []
        for leak in leaks if isinstance(leaks, list) else []:
            rule = str(leak.get("RuleID", "unknown")) if isinstance(leak, dict) else "unknown"
            start = leak.get("StartLine") if isinstance(leak, dict) else None
            origin = (
                added[start - 1] if isinstance(start, int) and 1 <= start <= len(added) else None
            )
            findings.append(_finding(rule, origin))
        return findings or [Finding(message="a possible secret was added", target="diff")]


def _finding(rule: str, origin: AddedLine | None) -> Finding:
    message = f"a possible secret was added (rule {rule})"
    if origin is None or origin.path is None:
        return Finding(message=message, target="diff")
    try:
        place = Location(path=origin.path, line=origin.number)
    except ValidationError:
        return Finding(message=message, target=origin.path)
    return Finding(message=message, target=origin.path, location=place)
