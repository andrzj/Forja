"""The measurer of a real run: the gate pipeline over an adapter's tools.

It formats the base, measures it (build, tests twice to find the unstable ones, lint and
complexity totals), and judges each attempt and each integration with the checks in gate order.
"""

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Protocol

from pydantic import JsonValue

from forja.checks.base import Undecided, measure, overrides_from
from forja.checks.build_and_tests import FAILED, BuildCheck, TestsCheck
from forja.checks.changes import Changes, read_before, read_changes
from forja.checks.complexity import ComplexityCheck, lizard_plan, parse_functions
from forja.checks.coverage import CoverageShare
from forja.checks.crap import CrapCheck
from forja.checks.freeze import FreezeCheck
from forja.checks.layout import SOURCE_SUFFIXES, FormatCheck, LintCheck, violations
from forja.checks.module_depth import ModuleDepthCheck
from forja.checks.mutation import MutationCheck
from forja.checks.pass_through import PassThroughCheck
from forja.checks.red_green import RedGreenCheck
from forja.checks.scope import ScopeCheck
from forja.checks.secrets import SecretsCheck
from forja.checks.structure import SUFFIXES as SHAPE_SUFFIXES
from forja.checks.tooling import Tools
from forja.core.adapters import (
    CommandPlan,
    FileClass,
    LanguageAdapter,
    Operation,
    OperationRequest,
)
from forja.core.artifacts.models import Producer
from forja.core.atomic import atomic_write_bytes
from forja.core.events import EventLog, LogEventSink, OpenOperation
from forja.core.gates import (
    Check,
    CheckSettings,
    GateInput,
    GatePipeline,
    Inconclusive,
    PipelineOutcome,
)
from forja.core.idempotency import Decision, Reconciliation
from forja.core.states import Level
from forja.orchestrator.ports import AttemptContext, Baseline, Expectations, SinkFactory

BASE_FILE = "base.json"
HEAD = "HEAD"
UNSTABLE = "unstable"
PASSING = "passing"


class GitAt(Protocol):
    """A git that can be pointed at another worktree (``GuardedGit`` is one)."""

    async def lines(self, *args: str) -> list[str]: ...

    def at(self, repo: Path) -> "GitAt": ...


class PipelineMeasurer:
    def __init__(
        self,
        *,
        adapter: LanguageAdapter,
        git: GitAt,
        log: EventLog,
        workdir: Path,
        host_env: Mapping[str, str],
        settings: Mapping[str, CheckSettings],
        values: Mapping[str, Mapping[str, JsonValue]] | None = None,
        lizard: tuple[str, ...],
        gitleaks: tuple[str, ...] = ("gitleaks",),
        timeouts: Mapping[str, float] | None = None,
    ) -> None:
        self._adapter = adapter
        self._git = git
        self._log = log
        self._workdir = workdir
        self._env = host_env
        self._settings = settings
        self._values = values or {}
        self._lizard = lizard
        self._gitleaks = gitleaks
        self._timeouts = timeouts or {}

    # -- helpers -------------------------------------------------------------------------------

    @property
    def _run_id(self) -> str:
        return self._log.state.run_id

    def _tools(self, sinks: SinkFactory, level: Level, target: str) -> Tools:
        return Tools(
            sinks=sinks,
            log=self._log,
            level=level,
            target=target,
            logs=self._workdir / "tools" / target,
            host_env=self._env,
            timeouts=self._timeouts,
        )

    def _classify(self, path: str) -> FileClass:
        return self._adapter.classify(path) or FileClass.OTHER

    def _run_sink(self, level: Level, target: str, operation: str) -> LogEventSink:
        return LogEventSink(self._log, level, target, operation)

    @property
    def _base_file(self) -> Path:
        return self._workdir / BASE_FILE

    def _read_base(self) -> tuple[frozenset[str], frozenset[str]]:
        """The unstable tests and the ones that passed, as the first measurement saw them."""
        try:
            data = json.loads(self._base_file.read_text(encoding="utf-8"))
            return frozenset(map(str, data[UNSTABLE])), frozenset(map(str, data[PASSING]))
        except (OSError, ValueError, KeyError, TypeError):
            return frozenset(), frozenset()

    # -- normalization -------------------------------------------------------------------------

    async def format_worktree(self, worktree: Path) -> None:
        """Safe lint fixes, then the formatter, over the whole tree: the ``style:`` commit."""
        tools = self._tools(self._run_sink, Level.EXECUTION, self._run_id)
        for operation, name in (
            (Operation.LINT_FIX, "normalize_lint"),
            (Operation.FORMAT, "normalize_format"),
        ):
            plan = self._adapter.plan(operation, OperationRequest(root=worktree))
            if isinstance(plan, CommandPlan):
                await tools.run(name, plan)

    # -- the base ------------------------------------------------------------------------------

    async def baseline(self, worktree: Path, sinks: SinkFactory) -> Baseline:
        tools = self._tools(sinks, Level.EXECUTION, self._run_id)
        problems: list[str] = []
        try:
            problems += await self._build_problems(tools, worktree)
            first = await self._outcomes(tools, worktree)
            second = await self._outcomes(tools, worktree)
        except Undecided as stop:
            return Baseline(False, (_describe(stop),))
        failing = {t for t, o in first.items() if o in FAILED} & {
            t for t, o in second.items() if o in FAILED
        }
        unstable = sorted(t for t in first.keys() | second.keys() if first.get(t) != second.get(t))
        problems += [f"tests: {t} fails on the base" for t in sorted(failing)]
        if not self._base_file.exists():
            stable = sorted(
                t for t, o in first.items() if o == "passed" and second.get(t) == "passed"
            )
            self._save_base(unstable, stable)
        metrics = await self._metrics(tools, worktree, len(first), len(unstable))
        return Baseline(not problems, tuple(problems), metrics)

    def _overrides(self, check_id: str) -> dict[str, dict[str, tuple[str, ...]]]:
        """The repository's own command for this check, if its ``forja.toml`` names one."""
        return overrides_from(self._adapter, self._values.get(check_id, {}))

    def _save_base(self, unstable: list[str], passing: list[str]) -> None:
        self._workdir.mkdir(parents=True, exist_ok=True)
        document = json.dumps({UNSTABLE: unstable, PASSING: passing}, sort_keys=True)
        atomic_write_bytes(self._base_file, document.encode("utf-8"))

    async def _build_problems(self, tools: Tools, worktree: Path) -> list[str]:
        parsed = await measure(
            tools,
            self._adapter,
            Operation.BUILD,
            "build",
            OperationRequest(root=worktree),
            self._overrides("build"),
        )
        return [f"build: {d.target.id} does not compile" for d in parsed.drafts]

    async def _outcomes(self, tools: Tools, worktree: Path) -> dict[str, str]:
        parsed = await measure(
            tools,
            self._adapter,
            Operation.TEST,
            "tests",
            OperationRequest(root=worktree),
            self._overrides("tests"),
        )
        return {d.target.id: str(d.value) for d in parsed.drafts if d.measurement == "test.outcome"}

    async def _metrics(
        self, tools: Tools, worktree: Path, tests: int, unstable: int
    ) -> dict[str, float]:
        metrics: dict[str, float] = {"tests": float(tests), "unstable_tests": float(unstable)}
        try:
            lint = await measure(
                tools,
                self._adapter,
                Operation.LINT,
                "lint",
                OperationRequest(root=worktree),
                self._overrides("lint"),
            )
            metrics["lint_violations"] = float(sum(violations(lint.drafts).values()))
        except Undecided:
            pass  # a metric that could not be taken is left out, not made up
        files = await self._production_files(worktree)
        if files:
            try:
                complexity = await self._complexity(tools, worktree, files)
            except Undecided:
                return metrics
            metrics["max_ccn"] = float(max(complexity.values(), default=0))
            metrics["functions"] = float(len(complexity))
        return metrics

    async def _production_files(self, worktree: Path) -> tuple[str, ...]:
        listed = await self._git.at(worktree).lines("ls-files")
        return tuple(
            p
            for p in listed
            if p.endswith(SOURCE_SUFFIXES) and self._classify(p) is FileClass.PRODUCTION
        )

    async def _complexity(
        self, tools: Tools, worktree: Path, files: tuple[str, ...]
    ) -> dict[tuple[str, str], int]:
        plan = lizard_plan(self._lizard, worktree, files)
        execution = await tools.run("complexity", plan)
        if not execution.finished or execution.result.exit_code != 0:
            raise Undecided(execution.inconclusive("complexity"))
        return parse_functions(execution.lines)

    async def functions(self, worktree: Path, sinks: SinkFactory) -> dict[tuple[str, str], int]:
        """The cyclomatic complexity of every function of the production code, for the planner."""
        files = await self._production_files(worktree)
        if not files:
            return {}
        tools = self._tools(sinks, Level.EXECUTION, self._run_id)
        try:
            return await self._complexity(tools, worktree, files)
        except Undecided as stop:
            raise RuntimeError(f"the complexity could not be measured: {_describe(stop)}") from None

    # -- attempts and integration -------------------------------------------------------------

    async def judge(
        self, ctx: AttemptContext, sinks: SinkFactory, expectations: Expectations | None = None
    ) -> PipelineOutcome:
        git = self._git.at(ctx.worktree)
        changes = await read_changes(git)
        before = await read_before(git, changes, SOURCE_SUFFIXES)
        # an extra test stage judges the code the implementer committed, read against what it was
        base = await self._code_base(git, ctx.task.reviews)
        code = changes if base == HEAD else await read_changes(git, base)
        code_before = (
            before if base == HEAD else await read_before(git, code, SOURCE_SUFFIXES, base)
        )
        before_shapes = await read_before(git, code, SHAPE_SUFFIXES, base)
        tools = self._tools(sinks, Level.ATTEMPT, ctx.attempt_id)
        production = tuple(p for p in code.current() if self._classify(p) is FileClass.PRODUCTION)
        unstable, passing = self._read_base()
        adapter, worktree = self._adapter, ctx.worktree
        share = CoverageShare()
        checks: list[Check] = [
            ScopeCheck(changes, ctx.task, self._classify),
            *self._frozen(ctx, changes),
            SecretsCheck(
                tools, worktree, changes, self._workdir / "secrets" / ctx.attempt_id, self._gitleaks
            ),
            FormatCheck(tools, adapter, worktree, changes),
            LintCheck(tools, adapter, worktree, changes, before),
            BuildCheck(tools, adapter, worktree),
            self._tests_check(ctx, tools, expectations, unstable, passing),
            MutationCheck(tools, adapter, worktree, code, production, self._env, share=share),
            ComplexityCheck(tools, worktree, code, production, code_before, self._lizard),
            CrapCheck(
                tools, adapter, worktree, code, production, code_before, self._lizard, share=share
            ),
            PassThroughCheck(worktree, code, production, before_shapes),
            ModuleDepthCheck(worktree, code, production, before_shapes),
        ]
        head = (await git.lines("rev-parse", "HEAD"))[0]
        data = GateInput(worktree, head, ctx.task.task_id, ctx.task.stage_id, ctx.attempt_id)
        return await self._pipeline(checks).run(data, _capabilities(adapter))

    async def _code_base(self, git: GitAt, stage: str) -> str:
        """The commit before the one that holds the work of ``stage``; ``HEAD`` for no stage."""
        if not stage:
            return HEAD
        found = await git.lines("log", "-1", "--format=%H", f"--grep=^Stage-Id: {stage}$")
        if not found:
            raise RuntimeError(f"the work of stage {stage} is not in the history")
        return f"{found[0]}^"

    def _frozen(self, ctx: AttemptContext, changes: Changes) -> list[Check]:
        task = ctx.task
        if not (task.frozen_digest and task.test_root):
            return []
        return [FreezeCheck(ctx.worktree, changes, task.test_root, task.frozen_digest)]

    def _tests_check(
        self,
        ctx: AttemptContext,
        tools: Tools,
        expectations: Expectations | None,
        unstable: frozenset[str],
        passing: frozenset[str],
    ) -> Check:
        """The test author's tests are red on purpose, so its stage has its own judge of them;
        the tests of an extra stage describe code that exists, so they must pass."""
        if ctx.task.role is not Producer.TEST_AUTHOR or ctx.task.reviews:
            return TestsCheck(tools, self._adapter, ctx.worktree, unstable, passing)
        assert expectations is not None  # the cycle gives them to every test author stage
        return RedGreenCheck(
            tools,
            self._adapter,
            ctx.worktree,
            self._classify,
            expectations.criteria,
            expectations.declared,
            unstable,
            passing,
        )

    async def integration(self, worktree: Path, sinks: SinkFactory) -> PipelineOutcome:
        git = self._git.at(worktree)
        tools = self._tools(sinks, Level.EXECUTION, self._run_id)
        unstable, passing = self._read_base()
        checks: list[Check] = [
            BuildCheck(tools, self._adapter, worktree),
            TestsCheck(tools, self._adapter, worktree, unstable, passing),
        ]
        head = (await git.lines("rev-parse", "HEAD"))[0]
        data = GateInput(worktree, head, "integration", "integration", "integration")
        return await self._pipeline(checks).run(data, _capabilities(self._adapter))

    def _pipeline(self, checks: list[Check]) -> GatePipeline:
        return GatePipeline(checks, self._settings, self._values)

    async def reconcile(self, operation: OpenOperation) -> Reconciliation:
        """A tool run changes nothing the next one depends on, so it is simply run again."""
        return Reconciliation(Decision.REDO)


def _capabilities(adapter: LanguageAdapter) -> set[str]:
    return {capability.value for capability in adapter.capabilities}


def _describe(stop: Undecided) -> str:
    result = stop.result
    if isinstance(result, Inconclusive):
        return result.detail
    return f"not applicable: {result.missing_capability}"
