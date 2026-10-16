"""Gate 7 (the mutation part): do the tests notice a change to the lines the attempt wrote?

Only the lines the diff added are mutated. As in unclebob/mutator, coverage only says which lines
a test runs (a mutant on another line is not run), each mutant is judged by the whole test
command, and the score is killed over killed plus survived; one below the policy's limit reproves.
The tests of the adapter are Python's only, though the rules of the sites cover more languages.
"""

import itertools
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import ClassVar

from forja.checks.base import Undecided, decided, rejected
from forja.checks.changes import Changes, added_lines
from forja.checks.coverage import CoverageShare, run_coverage
from forja.checks.tooling import Tools
from forja.core.adapters import (
    LanguageAdapter,
    NotSupported,
    Operation,
    OperationRequest,
    build_spec,
)
from forja.core.gates import Approved, Finding, GateInput, GateResult, Inconclusive
from forja.core.gates.models import InconclusiveReason
from forja.core.process import Outcome, ProcessIdentity, ProcessRunner
from forja.core.reports.models import CoverageReport, MutantStatus, MutationReport
from forja.mutation.apply import apply_site
from forja.mutation.executor import (
    BaselineFailed,
    Mutant,
    TestsDidNotRun,
    TestVerdict,
    run_mutants,
)
from forja.mutation.sites import discover

DEFAULT_MIN_SCORE = 0.65
BASELINE_TIMEOUT = 600.0
SUFFIXES = (".py",)


def min_score(data: GateInput, language: str) -> float:
    thresholds = data.values.get("thresholds")
    per_language = thresholds.get(language) if isinstance(thresholds, dict) else None
    value = per_language.get("min_score") if isinstance(per_language, dict) else None
    ok = isinstance(value, int | float) and not isinstance(value, bool) and 0 < value <= 1
    return float(value) if ok and isinstance(value, int | float) else DEFAULT_MIN_SCORE


def worker_count(data: GateInput) -> int | None:
    limits = data.values.get("limits")
    value = limits.get("workers") if isinstance(limits, dict) else None
    ok = isinstance(value, int) and not isinstance(value, bool) and value > 0
    return value if ok and isinstance(value, int) else None


def changed_lines(changes: Changes, files: tuple[str, ...]) -> dict[str, frozenset[int]]:
    """The lines of ``files`` the attempt added, by file."""
    found: dict[str, set[int]] = {}
    for line in added_lines(changes.patch):
        if line.path in files and line.number is not None:
            found.setdefault(line.path, set()).add(line.number)
    return {path: frozenset(numbers) for path, numbers in found.items()}


def build_mutants(
    worktree: Path, lines: Mapping[str, frozenset[int]], coverage: CoverageReport
) -> list[Mutant]:
    """One mutant per place on a changed line where the rules allow a change."""
    mutants: list[Mutant] = []
    for path, wanted in sorted(lines.items()):
        try:
            source = (worktree / path).read_text(encoding="utf-8")
            sites = discover(source, path)
        except (OSError, SyntaxError, ValueError):
            continue  # a file that does not compile is the build gate's finding, not this one's
        for site in sites:
            if site.line not in wanted:
                continue
            mutated = apply_site(source, site).encode("utf-8")
            covered = coverage.is_covered(path, site.line)
            mutants.append(
                Mutant(path, site.line, site.description, site.function, mutated, covered)
            )
    return mutants


class _Quiet:
    """Thousands of mutant runs are not events anyone reads."""

    def intent(self, operation_id: str, details: Mapping[str, object]) -> None:
        pass

    def started(self, operation_id: str, identity: ProcessIdentity) -> None:
        pass

    def progress(self, operation_id: str, channel: str, line: str) -> None:
        pass

    def effect(self, operation_id: str, details: Mapping[str, object]) -> None:
        pass


@dataclass(frozen=True)
class AdapterRunner:
    """Runs the adapter's whole test command in a copy of the repository."""

    __test__: ClassVar[bool] = False  # not a test class, whatever its name says to pytest

    adapter: LanguageAdapter
    host_env: Mapping[str, str]
    logs: Path
    ids: "itertools.count[int]" = field(default_factory=itertools.count)

    async def __call__(self, root: Path, timeout: float | None) -> TestVerdict:
        plan = self.adapter.plan(Operation.TEST, OperationRequest(root=root))
        if isinstance(plan, NotSupported):
            raise TestsDidNotRun(plan.reason)
        # a stale bytecode file could run the original code in place of the mutant
        env = {**plan.env_set, "PYTHONDONTWRITEBYTECODE": "1"}
        spec = build_spec(replace(plan, env_set=env), self.host_env, timeout=timeout)
        number = next(self.ids)
        log = self.logs / f"mutant-{number}.log"
        self.logs.mkdir(parents=True, exist_ok=True)
        try:
            result = await ProcessRunner(_Quiet()).run(f"mutant:{number}", spec, log)
        finally:
            log.unlink(missing_ok=True)
        if result.outcome is Outcome.TIMED_OUT:
            return TestVerdict.TIMED_OUT
        if result.outcome is not Outcome.EXITED:
            raise TestsDidNotRun(result.outcome.value)
        return TestVerdict.PASSED if result.exit_code == 0 else TestVerdict.FAILED


def _failed(detail: str) -> Undecided:
    return Undecided(Inconclusive(reason=InconclusiveReason.TOOL_FAILED, detail=detail))


@dataclass(frozen=True)
class MutationCheck:
    tools: Tools
    adapter: LanguageAdapter
    worktree: Path
    changes: Changes
    files: tuple[str, ...]  # production files the attempt changed
    host_env: Mapping[str, str]
    language: str = "python"
    id: str = "mutation"
    gate: int = 7
    requires: frozenset[str] = frozenset({"coverage"})
    share: CoverageShare | None = None

    async def evaluate(self, data: GateInput) -> GateResult:
        return await decided(self._judge(data))

    async def _judge(self, data: GateInput) -> GateResult:
        lines = changed_lines(self.changes, tuple(f for f in self.files if f.endswith(SUFFIXES)))
        if not lines:
            return Approved()
        coverage = await run_coverage(self.tools, self.adapter, self.worktree, data, self.share)
        mutants = build_mutants(self.worktree, lines, coverage)
        if not mutants:
            return Approved()
        report = await self._run(data, mutants)
        return self._verdict(report, min_score(data, self.language))

    async def _run(self, data: GateInput, mutants: list[Mutant]) -> MutationReport:
        with tempfile.TemporaryDirectory(prefix="forja-mutants-", ignore_cleanup_errors=True) as d:
            runner = AdapterRunner(self.adapter, self.host_env, Path(d) / "logs")
            try:
                return await run_mutants(
                    self.worktree,
                    Path(d) / "copies",
                    mutants,
                    runner,
                    workers=worker_count(data),
                    baseline_timeout=BASELINE_TIMEOUT,
                )
            except BaselineFailed:
                raise _failed("mutation: the tests do not pass on the unchanged copy") from None
            except TestsDidNotRun as error:
                raise _failed(f"mutation: the tests could not run ({error})") from None

    def _verdict(self, report: MutationReport, limit: float) -> GateResult:
        score = report.score
        if score is None or score >= limit:
            return Approved()
        bad = report.with_status(MutantStatus.SURVIVED)
        findings = [
            Finding(
                message="the tests do not notice enough changes to the new code",
                target="mutation",
                measured=round(score, 2),
                limit=limit,
            )
        ]
        findings += [
            Finding(
                message=f"change not noticed ({m.status.value}): {m.change}",
                target=f"{m.file}:{m.line}",
            )
            for m in bad
        ]
        return rejected(findings)
