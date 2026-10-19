"""Runs the adapter's coverage tool and reads what it wrote; mutation and CRAP share it."""

from dataclasses import dataclass
from pathlib import Path

from forja.checks.base import Undecided, overrides_from
from forja.checks.tooling import Tools
from forja.core.adapters import (
    CommandPlan,
    LanguageAdapter,
    Operation,
    OperationRequest,
    plan_with_override,
)
from forja.core.gates import GateInput, Inconclusive, NotApplicable
from forja.core.gates.models import InconclusiveReason
from forja.core.reports.formats import ReportSpec
from forja.core.reports.models import CoverageReport, FileCoverage
from forja.core.reports.readers import read_coverage
from forja.core.reports.reading import ReportError


def _failed(detail: str) -> Undecided:
    return Undecided(Inconclusive(reason=InconclusiveReason.TOOL_FAILED, detail=detail))


@dataclass
class CoverageShare:
    """Holds the coverage of one attempt so that two checks do not run the tests twice."""

    report: CoverageReport | None = None


async def run_coverage(
    tools: Tools,
    adapter: LanguageAdapter,
    worktree: Path,
    data: GateInput,
    share: CoverageShare | None = None,
) -> CoverageReport:
    """The coverage of the tests over ``worktree``; the report file is removed after it is read.

    With a ``share``, the first call measures and the later ones reuse the result.
    """
    if share is not None and share.report is not None:
        return share.report
    measured = await _measure(tools, adapter, worktree, data)
    if share is not None:
        share.report = measured
    return measured


async def _measure(
    tools: Tools, adapter: LanguageAdapter, worktree: Path, data: GateInput
) -> CoverageReport:
    report = getattr(adapter, "report", None)
    spec = report(Operation.COVERAGE) if callable(report) else None
    if not isinstance(spec, ReportSpec):
        raise Undecided(NotApplicable(missing_capability=Operation.COVERAGE.value))
    request = OperationRequest(root=worktree)
    overrides = overrides_from(adapter, data.values)
    plan = plan_with_override(adapter, Operation.COVERAGE, request, overrides)
    if not isinstance(plan, CommandPlan):
        raise Undecided(NotApplicable(missing_capability=Operation.COVERAGE.value))
    execution = await tools.run("coverage", plan)
    if not execution.finished:
        raise Undecided(execution.inconclusive("coverage"))
    paths = report_paths(worktree, spec.path)
    try:
        if execution.result.exit_code != 0:
            raise _failed(f"coverage: the tool ended with {execution.result.exit_code}")
        if not paths:
            raise OSError(f"{spec.path} was not written")
        return merge_coverage(
            [
                read_coverage(
                    spec.format,
                    path.read_text(encoding="utf-8"),
                    worktree,
                    spec.source_roots,
                )
                for path in paths
            ]
        )
    except (OSError, ReportError) as error:
        raise _failed(f"coverage: the report cannot be read ({error})") from None
    finally:
        for path in paths:
            path.unlink(missing_ok=True)  # the report is not part of the attempt


def report_paths(worktree: Path, pattern: str) -> list[Path]:
    """The report files; a pattern with ``*`` stands for a tool that puts them in a directory it
    names itself (a run id), one report per test project. A match that is a link, or that leaves
    the worktree through one, is not a report and is never read or removed."""
    if "*" not in pattern:
        return [worktree / pattern]
    inside = worktree.resolve()
    return sorted(
        path
        for path in worktree.glob(pattern)
        if path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(inside)
    )


def merge_coverage(reports: list[CoverageReport]) -> CoverageReport:
    """A line is covered if any report covers it; the tests that ran it add up."""
    if len(reports) == 1:
        return reports[0]
    merged: dict[str, FileCoverage] = {}
    for report in reports:
        for name, file in report.files.items():
            seen = merged.get(name)
            if seen is None:
                merged[name] = file
                continue
            covered = seen.covered | file.covered
            tests = {
                line: seen.tests.get(line, frozenset()) | file.tests.get(line, frozenset())
                for line in set(seen.tests) | set(file.tests)
            }
            merged[name] = FileCoverage(
                covered=covered, missed=(seen.missed | file.missed) - covered, tests=tests
            )
    return CoverageReport(merged)
