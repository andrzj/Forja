"""Gate 8 (the CRAP part): complex code that the tests barely run is the riskiest to change.

CRAP = CCN^2 * (1 - coverage)^3 + CCN, per function. Complexity comes from lizard, coverage from the
adapter's coverage tool over the lines of the function. As with complexity, a function above the
limit reproves only when it is new or got more complex: old risk is debt for the planner, not a
reason to refuse an unrelated improvement.
"""

import tempfile
from dataclasses import dataclass
from pathlib import Path

from forja.checks.base import decided, rejected
from forja.checks.changes import Changes, write_files
from forja.checks.complexity import Function, origin, read_spans
from forja.checks.coverage import CoverageShare, run_coverage
from forja.checks.tooling import Tools
from forja.core.adapters import LanguageAdapter
from forja.core.gates import Approved, Finding, GateInput, GateResult
from forja.core.reports.models import CoverageReport

DEFAULT_MAX_CRAP = 30.0  # the classic threshold; calibrated in step 9


def max_crap(data: GateInput, language: str) -> float:
    thresholds = data.values.get("thresholds")
    per_language = thresholds.get(language) if isinstance(thresholds, dict) else None
    value = per_language.get("max_crap") if isinstance(per_language, dict) else None
    ok = isinstance(value, int | float) and not isinstance(value, bool) and value > 0
    return float(value) if ok and isinstance(value, int | float) else DEFAULT_MAX_CRAP


def crap(ccn: int, coverage: float) -> float:
    """The CRAP score of a function with ``ccn`` paths of which ``coverage`` (0..1) is run."""
    return ccn * ccn * (1 - coverage) ** 3 + ccn


def coverage_of(report: CoverageReport, path: str, function: Function) -> float:
    """The share of the function's executable lines the tests run.

    A file the tool never saw counts as untested; a function with nothing executable has nothing
    left to test.
    """
    file = report.of(path)
    if file is None:
        return 0.0
    fraction = file.fraction(range(function.first, function.last + 1))
    return 1.0 if fraction is None else fraction


@dataclass(frozen=True)
class CrapCheck:
    tools: Tools
    adapter: LanguageAdapter
    worktree: Path
    changes: Changes
    files: tuple[str, ...]  # production files the attempt changed that lizard should read
    before: dict[str, str]  # the parent commit's text of those files, by old path
    lizard: tuple[str, ...]
    language: str = "python"
    id: str = "crap"
    gate: int = 8
    requires: frozenset[str] = frozenset({"structural_meters", "coverage"})
    share: CoverageShare | None = None

    async def evaluate(self, data: GateInput) -> GateResult:
        return await decided(self._judge(data))

    async def _judge(self, data: GateInput) -> GateResult:
        if not self.files:
            return Approved()
        limit = max_crap(data, self.language)
        after = await read_spans(self.tools, self.lizard, self.worktree, self.files)
        was = await self._before()
        # only a function that could break the limit needs the (costly) coverage run
        if not any(crap(f.ccn, 0.0) > limit for f in after.values()):
            return Approved()
        report = await run_coverage(self.tools, self.adapter, self.worktree, data, self.share)
        findings = []
        for (path, name), function in sorted(after.items()):
            old = was.get((origin(self.changes, path), name))
            if old is not None and function.ccn <= old.ccn:
                continue
            score = crap(function.ccn, coverage_of(report, path, function))
            if score > limit:
                message = f"function {name} is complex and little tested"
                target = f"{path}::{name}"
                findings.append(
                    Finding(message=message, target=target, measured=round(score, 1), limit=limit)
                )
        return rejected(findings) if findings else Approved()

    async def _before(self) -> dict[tuple[str, str], Function]:
        if not self.before:
            return {}
        with tempfile.TemporaryDirectory(prefix="forja-before-") as directory:
            write_files(self.before, Path(directory))
            return await read_spans(
                self.tools, self.lizard, Path(directory), tuple(sorted(self.before))
            )
