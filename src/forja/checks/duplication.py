"""Gate 8: the attempt adds no duplicated code to the production files it changed (the ratchet).

jscpd does the ratchet itself: it is given the commit the work is read against (``HEAD`` unless a
later stage judges code committed before it; the work itself is in the worktree) through
``--baseline-from-ref`` and marks a clone ``isNew`` when its content hash is not in that commit.
Only a new clone with a side in a changed production file reproves: old duplication is debt for the
planner, not a reason to refuse someone else's improvement. The thresholds and the ignored paths go
in a config file, as arrays, because the command line leaves their syntax open.
"""

import json
from dataclasses import dataclass
from pathlib import Path

from forja.checks.base import Undecided, decided, rejected
from forja.checks.duplication_report import Clone, CloneSide, read_clones
from forja.checks.tooling import Tools
from forja.core.adapters import CommandPlan
from forja.core.gates import (
    Approved,
    Finding,
    GateInput,
    GateResult,
    Inconclusive,
    InconclusiveReason,
    Location,
)

REPORT = "jscpd-report.json"


@dataclass(frozen=True)
class DuplicationCheck:
    tools: Tools
    worktree: Path
    production: tuple[str, ...]  # the changed production files that still exist
    reports: Path  # a directory outside the worktree for the config and the report
    jscpd: tuple[str, ...] = ("jscpd",)
    min_tokens: int = 50
    min_lines: int = 5
    ignore: tuple[str, ...] = ()  # globs, relative to the worktree (the test root, for one)
    base: str = "HEAD"  # the commit the work is read against, as for the other checks
    id: str = "duplication"
    gate: int = 8
    requires: frozenset[str] = frozenset()

    async def evaluate(self, data: GateInput) -> GateResult:
        return await decided(self._judge())

    async def _judge(self) -> GateResult:
        if not self.production:
            return Approved()
        clones = await self._scan()
        mine = frozenset(self.production)
        findings = [
            _finding(clone, side, other)
            for clone in clones
            if clone.is_new
            for side, other in ((clone.first, clone.second), (clone.second, clone.first))
            if side.path in mine
        ]
        return rejected(findings) if findings else Approved()

    async def _scan(self) -> tuple[Clone, ...]:
        self.reports.mkdir(parents=True, exist_ok=True)
        report = self.reports / REPORT
        report.unlink(missing_ok=True)
        config = self.reports / "jscpd.json"
        config.write_text(
            json.dumps(
                {"minTokens": self.min_tokens, "minLines": self.min_lines, "ignore": self.ignore}
            ),
            encoding="utf-8",
        )
        plan = CommandPlan(
            (
                *self.jscpd,
                "--config",
                str(config),
                "-r",
                "json",
                "-o",
                str(self.reports),
                "--baseline-from-ref",
                self.base,
                ".",
            ),
            self.worktree,
        )
        execution = await self.tools.run("duplication", plan)
        if not execution.finished:
            raise Undecided(execution.inconclusive("duplication"))
        code = execution.result.exit_code
        if code != 0:
            raise _failed(f"duplication: jscpd ended with {code}", execution.operation_id)
        clones = read_clones(report)
        if clones is None:
            raise _failed("duplication: the jscpd report cannot be read", execution.operation_id)
        return clones


def _finding(clone: Clone, side: CloneSide, other: CloneSide) -> Finding:
    message = f"{clone.lines} duplicated lines, also in {other.path}:{other.start}"
    return Finding(
        message=message,
        target=side.path,
        location=Location(path=side.path, line=max(side.start, 1)),
        measured=clone.lines,
        limit=0,
    )


def _failed(detail: str, operation_id: str) -> Undecided:
    return Undecided(
        Inconclusive(
            reason=InconclusiveReason.TOOL_FAILED, detail=detail, tool_run_ids=(operation_id,)
        )
    )
