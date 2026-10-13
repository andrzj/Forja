"""One task from its branch to its integration, written so it can start again from any log.

Every step asks the journal first, so running this after a crash continues where the log stops.
The implementer's attempts are numbered ``<task>-a<n>`` and its stage is ``<task>-s``. A fix task
has the test author first, with stage ``<task>-t`` and attempts ``<task>-ta<n>``; the task joins the
run only after its last stage is committed.
"""

from pathlib import Path

from pydantic import JsonValue

from forja.checks.freeze import tree_digest
from forja.core.adapters.executor import ErrorKind
from forja.core.artifacts.models import Producer
from forja.core.events.state import RunState
from forja.core.gates import CheckRun, Inconclusive, Rejected, Verdict
from forja.core.states import AttemptState, Level, StageState, TaskState
from forja.orchestrator.budget import consecutive_infra_failures, quality_attempts
from forja.orchestrator.config import Objective
from forja.orchestrator.outcome import StopRun
from forja.orchestrator.ports import (
    AgentResult,
    AttemptContext,
    Expectations,
    RejectedWork,
    RunContext,
    TaskInfo,
)
from forja.orchestrator.workspace_git import CommitMessage

REASON_LIMIT = 1500
_FINISHED = (AttemptState.REJECTED, AttemptState.DISCARDED, AttemptState.COMMITTED)


def _count(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def describe_stop(run: CheckRun) -> str:
    """What the next attempt is told when a check stopped the last one."""
    result = run.result
    where = f"gate {run.gate} ({run.check_id})"
    if isinstance(result, Rejected):
        text = "; ".join(finding.describe() for finding in result.findings)
    elif isinstance(result, Inconclusive):
        text = f"inconclusive ({result.reason.value}): {result.detail}"
    else:
        text = result.result
    return f"{where}: {text}"[:REASON_LIMIT]


class TaskCycle:
    def __init__(self, ctx: RunContext) -> None:
        self._ctx = ctx
        self._journal = ctx.journal
        self._log = ctx.journal.log

    @property
    def _state(self) -> RunState:
        return self._log.state

    # -- the task -------------------------------------------------------------------------------

    def roles(self, task_id: str) -> tuple[Producer, ...]:
        """The stages of the task, in order; a task whose plan names none has the implementer's."""
        payload = self._state.transition_payload(Level.TASK, task_id, TaskState.PENDING) or {}
        named = payload.get("stages")
        roles = tuple(Producer(str(name)) for name in named) if isinstance(named, list) else ()
        return roles or (Producer.IMPLEMENTER,)

    def info(self, task_id: str, role: Producer = Producer.IMPLEMENTER) -> TaskInfo:
        """The task as seen by the stage of ``role``. The implementer's ids are the ones a task
        with a single stage always had, so a log from before two-stage tasks reads the same."""
        payload = self._state.transition_payload(Level.TASK, task_id, TaskState.PENDING) or {}
        scope = payload.get("scope")
        author = role is Producer.TEST_AUTHOR
        test_root = str(payload.get("test_root", ""))
        return TaskInfo(
            task_id,
            f"{task_id}-t" if author else f"{task_id}-s",
            str(payload.get("intent", "")),
            tuple(str(p) for p in scope) if isinstance(scope, list) else (),
            _count(payload.get("max_files")),
            _count(payload.get("max_lines")),
            role,
            test_root,
            f"{task_id}-ta" if author else f"{task_id}-a",
            "" if author else self._frozen_digest(task_id),
        )

    def _frozen_digest(self, task_id: str) -> str:
        """What the test author's stage froze, read from its commit; empty if it had none."""
        if Producer.TEST_AUTHOR not in self.roles(task_id):
            return ""
        frozen = self._state.transition_payload(Level.STAGE, f"{task_id}-t", StageState.COMMITTED)
        return str(frozen["frozen_digest"]) if frozen and "frozen_digest" in frozen else ""

    async def run(self, task_id: str) -> None:
        ctx, journal = self._ctx, self._journal
        journal.enter(Level.TASK, task_id, TaskState.IN_PROGRESS)
        await journal.operate(
            "create_task_branch",
            Level.TASK,
            task_id,
            task_id,
            ctx.workspace.create_task_branch(task_id),
        )
        for role in self.roles(task_id):
            info = self.info(task_id, role)
            if not await self._stage(info):
                return
        await self._integrate(self.info(task_id))

    async def _stage(self, info: TaskInfo) -> bool:
        """Work one stage until it is committed or stops the task; ``True`` if it was committed."""
        journal = self._journal
        journal.enter(Level.STAGE, info.stage_id, StageState.PENDING, parent=info.task_id)
        journal.enter(Level.STAGE, info.stage_id, StageState.IN_PROGRESS)
        if self._state.state_of(Level.STAGE, info.stage_id) is StageState.INFRA_PAUSED:
            self._log.append_transition(
                Level.STAGE, info.stage_id, StageState.INFRA_PAUSED, StageState.IN_PROGRESS
            )
        while (attempt := self._next_attempt(info)) is not None:
            await self._attempt(info, attempt)
        stage = self._state.state_of(Level.STAGE, info.stage_id)
        if stage is StageState.EXHAUSTED:
            payload = self._state.transition_payload(
                Level.STAGE, info.stage_id, StageState.EXHAUSTED
            )
            journal.enter(Level.TASK, info.task_id, TaskState.BLOCKED, payload=payload)
        return stage is StageState.COMMITTED

    def _next_attempt(self, info: TaskInfo) -> str | None:
        state, journal = self._state, self._journal
        children = state.children_of(Level.ATTEMPT, info.stage_id)
        for attempt in children:
            if not journal.done("remove_worktree", attempt):
                return attempt
        if state.state_of(Level.STAGE, info.stage_id) is not StageState.IN_PROGRESS:
            return None
        budget = self._ctx.config.budget
        if quality_attempts(state, info.stage_id) >= budget.attempts_per_task:
            self._exhaust(info, "attempts_exhausted")
            return None
        if self._ctx.meter.exhausted():
            self._exhaust(info, "token_budget_exhausted")
            return None
        return f"{info.attempt_prefix}{len(children) + 1}"

    def _exhaust(self, info: TaskInfo, reason: str) -> None:
        self._log.append_transition(
            Level.STAGE,
            info.stage_id,
            StageState.IN_PROGRESS,
            StageState.EXHAUSTED,
            payload={"reason": reason},
        )

    # -- one attempt ----------------------------------------------------------------------------

    async def _attempt(self, info: TaskInfo, attempt: str) -> None:
        ctx, journal = self._ctx, self._journal
        journal.enter(Level.ATTEMPT, attempt, AttemptState.CREATED, parent=info.stage_id)
        if self._state.state_of(Level.ATTEMPT, attempt) not in _FINISHED:
            attempt_ctx = AttemptContext(
                info, attempt, ctx.workspace.attempt_worktree(attempt), self._last_rejection(info)
            )
            await self._work(attempt_ctx)
        elif self._state.state_of(Level.ATTEMPT, attempt) is AttemptState.COMMITTED:
            # cut between the attempt's commit and the stage's: finish what _commit started
            journal.enter(
                Level.STAGE,
                info.stage_id,
                StageState.COMMITTED,
                payload=self._frozen(info, ctx.workspace.attempt_worktree(attempt)),
            )
        await journal.operate(
            "remove_worktree",
            Level.ATTEMPT,
            attempt,
            attempt,
            ctx.workspace.remove_worktree(attempt),
        )

    def _last_rejection(self, info: TaskInfo) -> str | None:
        state = self._state
        for attempt in reversed(state.children_of(Level.ATTEMPT, info.stage_id)):
            if state.state_of(Level.ATTEMPT, attempt) is AttemptState.REJECTED:
                payload = state.transition_payload(Level.ATTEMPT, attempt, AttemptState.REJECTED)
                assert payload is not None  # _reject always says why
                return str(payload["reason"])
        return None

    async def _work(self, ctx: AttemptContext) -> None:
        run, journal = self._ctx, self._journal
        attempt, task = ctx.attempt_id, ctx.task.task_id
        await journal.operate(
            "create_attempt_worktree",
            Level.ATTEMPT,
            attempt,
            attempt,
            run.workspace.create_attempt_worktree(task, attempt),
        )
        await journal.operate(
            "prepare_workcopy",
            Level.ATTEMPT,
            attempt,
            attempt,
            run.runner(ctx.task.role).prepare_workcopy(ctx),
        )
        journal.enter(Level.ATTEMPT, attempt, AttemptState.WORKCOPY_READY)
        journal.enter(Level.ATTEMPT, attempt, AttemptState.AGENT_RUNNING)

        if self._state.state_of(Level.ATTEMPT, attempt) is AttemptState.AGENT_RUNNING:
            called = await self._call_agent(ctx)
            if called is None:
                await self._result_lost(ctx.task, attempt)
                return
            result, differences = called
            if result.error is not None:
                await self._infrastructure_failed(ctx.task, attempt, result)
                return
            journal.enter(
                Level.ATTEMPT,
                attempt,
                AttemptState.VALIDATING,
                payload={"reason": result.reason[:REASON_LIMIT]},
            )
            if differences:
                reason = "git changed while the agent ran: " + "; ".join(differences)
                self._reject(attempt, reason)
                # the repository was touched outside the contract: more attempts would start from
                # a state nobody approved, so the run stops and says why
                raise StopRun(reason[:REASON_LIMIT])

        if self._state.state_of(Level.ATTEMPT, attempt) is AttemptState.VALIDATING:
            await self._judge(ctx)
        if self._state.state_of(Level.ATTEMPT, attempt) is AttemptState.APPROVED:
            await self._commit(ctx)

    async def _call_agent(self, ctx: AttemptContext) -> tuple[AgentResult, list[str]] | None:
        """The call and what git looked like around it; ``None`` if the call ended earlier."""
        run = self._ctx
        op_id = self._journal.operation_id("call_agent_cli", ctx.attempt_id)
        if op_id is None:
            return None
        async with run.workspace.watch() as watch:
            result = await run.runner(ctx.task.role).call(
                ctx, op_id, run.sinks(Level.ATTEMPT, ctx.attempt_id, "call_agent_cli")
            )
        return result, [difference.describe() for difference in watch.differences]

    def _reject(self, attempt: str, reason: str) -> None:
        self._log.append_transition(
            Level.ATTEMPT,
            attempt,
            self._state.state_of(Level.ATTEMPT, attempt),
            AttemptState.REJECTED,
            payload={"reason": reason[:REASON_LIMIT]},
        )

    async def _judge(self, ctx: AttemptContext) -> None:
        run, journal = self._ctx, self._journal
        attempt = ctx.attempt_id
        try:
            await journal.operate(
                "apply_diff",
                Level.ATTEMPT,
                attempt,
                attempt,
                run.runner(ctx.task.role).apply_diff(ctx),
            )
        except RejectedWork as rejected:
            self._reject(attempt, str(rejected))
            return
        outcome = await run.measurer.judge(ctx, run.sinks, self._expectations(ctx))
        for assumption in outcome.assumptions:
            journal.note(
                "premise",
                {"task": ctx.task.task_id, "attempt": attempt, "check": assumption.check_id},
            )
        stopper = outcome.stopped_by
        if stopper is None:
            journal.enter(Level.ATTEMPT, attempt, AttemptState.APPROVED)
        elif outcome.verdict is Verdict.REJECTED:
            self._reject(attempt, describe_stop(stopper))
        else:
            self._block(ctx.task, attempt, describe_stop(stopper))

    def _expectations(self, ctx: AttemptContext) -> Expectations | None:
        fix = self._ctx.config.fix
        if ctx.task.role is not Producer.TEST_AUTHOR or fix is None:
            return None
        declared = self._ctx.runner(ctx.task.role).declared_tests(ctx)
        return Expectations(frozenset(int(c.id) for c in fix.criteria.criteria), declared)

    def _block(self, info: TaskInfo, attempt: str, detail: str) -> None:
        """A gate could not judge and its policy is to block: not the agent's fault, not counted."""
        self._log.append_transition(
            Level.ATTEMPT,
            attempt,
            AttemptState.VALIDATING,
            AttemptState.DISCARDED,
            payload={
                "reason": "inconclusive_gate",
                "detail": detail[:REASON_LIMIT],
                "infra_failure": False,
            },
        )
        self._exhaust(info, "inconclusive_gate")

    async def _commit(self, ctx: AttemptContext) -> None:
        run, journal = self._ctx, self._journal
        attempt, info = ctx.attempt_id, ctx.task
        validating = self._state.transition_payload(Level.ATTEMPT, attempt, AttemptState.VALIDATING)
        assert validating is not None  # _work records the agent's reason on the way in
        reason = str(validating["reason"])
        author = info.role is Producer.TEST_AUTHOR
        executor = (
            (run.config.test_author or run.config.implementer)
            if author
            else (run.config.implementer)
        )
        kind = "test" if author else "fix" if run.config.objective is Objective.FIX else "refactor"
        message = CommitMessage.of(
            kind,
            info.intent,
            reason,
            agent=f"{executor.name} {executor.version}",
            policy_version=run.config.policy_version,
        )
        await journal.operate(
            "commit_stage",
            Level.ATTEMPT,
            attempt,
            attempt,
            run.workspace.commit_stage(info.task_id, info.stage_id, attempt, message),
        )
        journal.enter(Level.ATTEMPT, attempt, AttemptState.COMMITTED)
        journal.enter(
            Level.STAGE,
            info.stage_id,
            StageState.COMMITTED,
            payload=self._frozen(info, ctx.worktree),
        )

    @staticmethod
    def _frozen(info: TaskInfo, worktree: Path) -> dict[str, JsonValue] | None:
        """The test author freezes its tests; the implementer must leave them as they are."""
        if info.role is not Producer.TEST_AUTHOR or not info.test_root:
            return None
        return {"frozen_digest": tree_digest(worktree, info.test_root)}

    # -- infrastructure failures ----------------------------------------------------------------

    async def _infrastructure_failed(
        self, info: TaskInfo, attempt: str, result: AgentResult
    ) -> None:
        run = self._ctx
        error = result.error
        assert error is not None
        self._log.append_transition(
            Level.ATTEMPT,
            attempt,
            AttemptState.AGENT_RUNNING,
            AttemptState.DISCARDED,
            payload={
                "reason": error.kind.value,
                "detail": error.message[:300],
                "infra_failure": True,
            },
        )
        if error.kind is ErrorKind.BLOCKING:
            self._stage_pause(info)
            raise StopRun(f"the agent cannot continue: {error.message}")
        failures = consecutive_infra_failures(self._state, info.stage_id)
        if failures >= run.config.budget.infra_failures:
            self._stage_pause(info)
            raise StopRun(f"{failures} infrastructure failures in a row on {info.task_id}")
        if error.kind is ErrorKind.TRANSIENT:
            await run.sleep(run.backoff[min(failures, len(run.backoff)) - 1])
        elif not await self._network_came_back():
            self._stage_pause(info)
            raise StopRun("the network did not come back")

    async def _result_lost(self, info: TaskInfo, attempt: str) -> None:
        """The call ended but the run died before it could say how: that cannot be trusted.

        Whether the agent reported an error, or reached outside its copy, went with the process.
        Judging the work as if nothing had happened would fail open, so the attempt is dropped and
        counts as an infrastructure failure, like a call that cannot be verified.
        """
        self._log.append_transition(
            Level.ATTEMPT,
            attempt,
            AttemptState.AGENT_RUNNING,
            AttemptState.DISCARDED,
            payload={"reason": "result_lost", "infra_failure": True},
        )
        failures = consecutive_infra_failures(self._state, info.stage_id)
        if failures >= self._ctx.config.budget.infra_failures:
            self._stage_pause(info)
            raise StopRun(f"{failures} infrastructure failures in a row on {info.task_id}")

    def _stage_pause(self, info: TaskInfo) -> None:
        if self._state.state_of(Level.STAGE, info.stage_id) is StageState.IN_PROGRESS:
            self._log.append_transition(
                Level.STAGE, info.stage_id, StageState.IN_PROGRESS, StageState.INFRA_PAUSED
            )

    async def _network_came_back(self) -> bool:
        run = self._ctx
        probes = 0
        while not run.meter.exhausted() and (
            run.max_network_probes is None or probes < run.max_network_probes
        ):
            probes += 1
            self._journal.note("waiting_for_network")
            await run.sleep(run.probe_interval)
            if await run.network_is_up():
                return True
        return False

    # -- the end of the task --------------------------------------------------------------------

    async def _integrate(self, info: TaskInfo) -> None:
        """Only after the last stage: a task with tests and no fix is not ready to join the run."""
        run, journal = self._ctx, self._journal
        task = info.task_id
        await journal.operate(
            "integrate_task",
            Level.TASK,
            task,
            task,
            run.workspace.integrate_task(task, f"merge: {info.intent}"),
        )
        if journal.done("rollback_integration", task):
            journal.enter(
                Level.TASK, task, TaskState.BLOCKED, payload={"reason": "integration_gate"}
            )
            return
        outcome = await run.measurer.integration(run.workspace.run_worktree, run.sinks)
        stopper = outcome.stopped_by
        if stopper is None:
            journal.enter(Level.TASK, task, TaskState.INTEGRATED)
            return
        await journal.operate(
            "rollback_integration", Level.TASK, task, task, run.workspace.rollback_integration(task)
        )
        journal.enter(
            Level.TASK,
            task,
            TaskState.BLOCKED,
            payload={"reason": "integration_gate", "detail": describe_stop(stopper)},
        )
