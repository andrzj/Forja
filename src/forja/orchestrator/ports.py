"""What the orchestrator needs from the world, as protocols.

Each port has its implementation in its own piece of increment 1 (git, the language adapter, the
agent runner); tests bring scripted ones. A port never writes to the event log: it returns steps
for the journal to run, or reports through the sinks the orchestrator hands it.
"""

import asyncio
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from types import TracebackType
from typing import Protocol

from forja.core.adapters.executor import ErrorActivity
from forja.core.artifacts.llm_output import DeclaredTest
from forja.core.artifacts.models import Producer
from forja.core.events import LogEventSink, OpenOperation
from forja.core.gates import PipelineOutcome
from forja.core.gitguard.snapshot import Difference
from forja.core.idempotency import Reconciliation
from forja.core.locking import IndexLockReport
from forja.core.process import EventSink
from forja.core.states import Level
from forja.orchestrator.budget import Meter
from forja.orchestrator.config import Budget, RunConfig
from forja.orchestrator.operations import Journal, Step
from forja.orchestrator.workspace_git import CommitMessage

# (level, target id, operation) -> where a process reports to; the orchestrator builds these.
SinkFactory = Callable[[Level, str, str], EventSink]


@dataclass(frozen=True)
class PlannedTask:
    """One unit of work the planner found: an intention, the files it may touch and its limits."""

    intent: str
    scope: tuple[str, ...]
    max_files: int
    max_lines: int
    stages: tuple[Producer, ...] = (Producer.IMPLEMENTER,)  # in order; a fix writes tests first
    test_root: str = ""  # where the test author may put tests; only for tasks that have one


@dataclass(frozen=True)
class Baseline:
    """The state of the code before any task: green or not, and the numbers to improve on."""

    ok: bool
    problems: tuple[str, ...] = ()
    metrics: Mapping[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class TaskInfo:
    """A task seen through one of its stages: ``stage_id`` and ``role`` are that stage's."""

    task_id: str
    stage_id: str
    intent: str
    scope: tuple[str, ...]
    max_files: int
    max_lines: int
    role: Producer = Producer.IMPLEMENTER
    test_root: str = ""
    attempt_prefix: str = ""  # attempts are ``<prefix><n>``; empty means ``<task>-a``
    frozen_digest: str = ""  # of the files under ``test_root`` the test author committed
    reviews: str = ""  # an extra test stage: the implementer stage whose committed code it tests


@dataclass(frozen=True)
class AttemptContext:
    task: TaskInfo
    attempt_id: str
    worktree: Path
    previous_rejection: str | None


@dataclass(frozen=True)
class Expectations:
    """What the test author owes: a test for each criterion, declared in its answer."""

    criteria: frozenset[int]
    declared: tuple[DeclaredTest, ...]


@dataclass(frozen=True)
class AgentResult:
    """How a call to the agent ended: why it says it did what it did, or what went wrong around it.

    ``error`` is a failure of the infrastructure, not of the work.
    """

    reason: str = ""
    error: ErrorActivity | None = None


class RejectedWork(Exception):
    """The work cannot even be judged (a symlink, names that differ only by case, a path too long
    for Windows). ``apply_diff`` raises it, so a resumed run finds the same problem again."""


class Planner(Protocol):
    async def plan(
        self, worktree: Path, baseline: Baseline, budget: Budget
    ) -> Sequence[PlannedTask]: ...


class Measurer(Protocol):
    async def format_worktree(self, worktree: Path) -> None: ...

    async def baseline(self, worktree: Path, sinks: SinkFactory) -> Baseline: ...

    async def judge(
        self, ctx: AttemptContext, sinks: SinkFactory, expectations: Expectations | None = None
    ) -> PipelineOutcome: ...

    async def integration(self, worktree: Path, sinks: SinkFactory) -> PipelineOutcome: ...

    async def reconcile(self, operation: OpenOperation) -> Reconciliation: ...


class AgentRunner(Protocol):
    def prepare_workcopy(self, ctx: AttemptContext) -> Step: ...

    async def call(
        self, ctx: AttemptContext, operation_id: str, sink: EventSink
    ) -> AgentResult: ...

    def apply_diff(self, ctx: AttemptContext) -> Step: ...

    def declared_tests(self, ctx: AttemptContext) -> tuple[DeclaredTest, ...]: ...

    async def reconcile(self, operation: OpenOperation) -> Reconciliation: ...


class Watch(Protocol):
    """A block around the agent's call that says afterwards what changed in git."""

    differences: list[Difference]

    async def __aenter__(self) -> "Watch": ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...


class Workspace(Protocol):
    """Git, seen as steps the journal can run once and a way to settle them after a crash."""

    run_branch: str

    @property
    def run_worktree(self) -> Path: ...

    def attempt_worktree(self, attempt_id: str) -> Path: ...

    async def check_ready(self) -> str: ...

    async def recover(self) -> IndexLockReport: ...

    def watch(self) -> Watch: ...

    def create_run_branch(self, base_commit: str) -> Step: ...

    def create_run_worktree(self) -> Step: ...

    def normalize_style(self, apply: Callable[[Path], Awaitable[None]]) -> Step: ...

    def create_task_branch(self, task_id: str) -> Step: ...

    def create_attempt_worktree(self, task_id: str, attempt_id: str) -> Step: ...

    def commit_stage(
        self, task_id: str, stage_id: str, attempt_id: str, message: CommitMessage
    ) -> Step: ...

    def integrate_task(self, task_id: str, subject: str) -> Step: ...

    def rollback_integration(self, task_id: str) -> Step: ...

    def remove_worktree(self, name: str) -> Step: ...

    async def reconcile(self, operation: OpenOperation) -> Reconciliation: ...


TEST_ROOT = (
    "tests"  # where the test author may put tests; the Python layout the 3a repositories use
)


async def _network_is_up() -> bool:
    return True


async def _no_test_files(worktree: Path) -> Sequence[str]:
    return ()


@dataclass
class RunContext:
    """Everything one run is made of, handed to the phases and to the task cycle."""

    journal: Journal
    config: RunConfig
    workspace: Workspace
    measurer: Measurer
    agent: AgentRunner  # the implementer's, and the default for a role without its own
    planner: Planner
    meter: Meter
    run_dir: Path
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep
    network_is_up: Callable[[], Awaitable[bool]] = _network_is_up
    backoff: tuple[float, ...] = (30.0, 60.0, 120.0)
    probe_interval: float = 60.0
    max_network_probes: int | None = None  # None waits for the network as long as it takes
    agents: Mapping[Producer, AgentRunner] = field(default_factory=dict)
    # the tracked test files of a worktree, for the digest the test author freezes; with none,
    # only what lies under the task's ``test_root`` is frozen
    test_files: Callable[[Path], Awaitable[Sequence[str]]] = _no_test_files
    test_root: str = TEST_ROOT  # where a test author with no root of its own writes

    def runner(self, role: Producer) -> AgentRunner:
        return self.agents.get(role, self.agent)

    def sinks(self, level: Level, target_id: str, operation: str) -> EventSink:
        return LogEventSink(self.journal.log, level, target_id, operation)
