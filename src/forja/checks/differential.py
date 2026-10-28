"""Gate 11: the new version gives the outputs the base gave for every declared case, at about the
same cost in time and memory.

Each case runs ``runs`` times on the attempt. An output that differs from the base by the case's own
rule is a finding (once per output, whichever run showed it). The time and the memory peak are
judged by the median of the runs against the median of the base, as a ratio: a run on a loaded
machine moves one value, not the median. A case the base showed to be unstable is left out. Memory
is judged only when both sides measured it.
"""

import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from forja.checks.base import Undecided, decided, rejected
from forja.checks.differential_base import BaseCase, DifferentialBase
from forja.checks.differential_compare import compare_output, describe
from forja.checks.differential_run import CHECK, CaseRun, run_case
from forja.checks.shape import threshold
from forja.checks.tooling import Tools
from forja.core.gates import (
    Approved,
    Finding,
    GateInput,
    GateResult,
    Inconclusive,
    InconclusiveReason,
    NotApplicable,
)
from forja.core.policy.differential import DifferentialCase

NO_CASES = "differential_cases"
NO_STABLE_CASES = "differential_stable_cases"
DEFAULT_MAX_TIME_RATIO = 1.25  # a guess until the calibration of queue item 6
DEFAULT_MAX_MEMORY_RATIO = 1.25
DEFAULT_RUNS = 3


@dataclass(frozen=True)
class _Limits:
    time: float
    memory: float
    runs: int


@dataclass(frozen=True)
class DifferentialCheck:
    """``cases`` and ``base`` are those of the run's frozen policy and of its base measurement.

    The thresholds are per language, and a case belongs to no language: the loosest value among
    ``languages`` (the languages of the project) is used.
    """

    tools: Tools
    cases: tuple[DifferentialCase, ...]
    base: DifferentialBase
    worktree: Path
    host_env: Mapping[str, str]
    languages: tuple[str, ...] = ()
    id: str = "differential"
    gate: int = 11
    requires: frozenset[str] = frozenset()

    async def evaluate(self, data: GateInput) -> GateResult:
        return await decided(self._judge(data))

    async def _judge(self, data: GateInput) -> GateResult:
        if not self.cases:
            return NotApplicable(missing_capability=NO_CASES)
        limits = _Limits(
            _loosest(data, self.languages, "max_time_ratio", DEFAULT_MAX_TIME_RATIO),
            _loosest(data, self.languages, "max_memory_ratio", DEFAULT_MAX_MEMORY_RATIO),
            max(1, int(_loosest(data, self.languages, "runs", DEFAULT_RUNS))),
        )
        findings: list[Finding] = []
        undecided: Undecided | None = None
        judged = 0
        for case in self.cases:
            kept = self.base.cases.get(case.name)
            if kept is None:
                undecided = undecided or Undecided(
                    Inconclusive(
                        reason=InconclusiveReason.TOOL_FAILED,
                        detail=f"{CHECK}: case {case.name}: the base has no measure of it",
                    )
                )
                continue
            if kept.quarantined:
                continue
            try:
                findings += await self._judge_case(case, kept, limits)
            except Undecided as stop:
                undecided = undecided or stop
                continue
            judged += 1
        if undecided is not None and not findings:  # a rejection wins over a run not made
            raise undecided
        if findings:
            return rejected(findings)
        return Approved() if judged else NotApplicable(missing_capability=NO_STABLE_CASES)

    async def _judge_case(
        self, case: DifferentialCase, kept: BaseCase, limits: _Limits
    ) -> list[Finding]:
        stdin = self.base.inputs.get(case.name)
        runs = [
            await run_case(self.tools, case, self.worktree, stdin, self.host_env)
            for _ in range(limits.runs)
        ]
        found = _differences(case, kept, runs)
        found += _slower(case, kept, runs, limits.time)
        found += _heavier(case, kept, runs, limits.memory)
        return found


def _loosest(data: GateInput, languages: Sequence[str], name: str, default: float) -> float:
    return max(
        (threshold(data, language, name, default) for language in languages), default=default
    )


def _differences(case: DifferentialCase, kept: BaseCase, runs: Sequence[CaseRun]) -> list[Finding]:
    found = []
    for output in case.outputs:
        key = (output.kind, output.path)
        for run in runs:
            account = compare_output(output, kept.outputs[key], run.outputs[key])
            if account is not None:
                found.append(
                    Finding(
                        message=f"the output differs from the base: {account}",
                        target=f"{case.name}: {describe(output)}",
                    )
                )
                break
    return found


def _slower(
    case: DifferentialCase, kept: BaseCase, runs: Sequence[CaseRun], limit: float
) -> list[Finding]:
    return _ratio(
        case.name, "slower than the base", [r.duration for r in runs], kept.durations, limit
    )


def _heavier(
    case: DifferentialCase, kept: BaseCase, runs: Sequence[CaseRun], limit: float
) -> list[Finding]:
    now = [r.peak_memory for r in runs if r.peak_memory is not None]
    return _ratio(case.name, "uses more memory than the base", now, kept.memories, limit)


def _ratio(
    target: str, message: str, now: Sequence[float], before: Sequence[float], limit: float
) -> list[Finding]:
    if not now or not before or statistics.median(before) <= 0:
        return []
    ratio = statistics.median(now) / statistics.median(before)
    if ratio <= limit:
        return []
    return [Finding(message=message, target=target, measured=round(ratio, 2), limit=limit)]
