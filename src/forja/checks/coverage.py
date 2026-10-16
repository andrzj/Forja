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
from forja.core.reports.models import CoverageReport
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
    path = worktree / spec.path
    try:
        if execution.result.exit_code != 0:
            raise _failed(f"coverage: the tool ended with {execution.result.exit_code}")
        text = path.read_text(encoding="utf-8")
        return read_coverage(spec.format, text, worktree)
    except (OSError, ReportError) as error:
        raise _failed(f"coverage: the report cannot be read ({error})") from None
    finally:
        path.unlink(missing_ok=True)  # the report is not part of the attempt
