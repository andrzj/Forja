"""One task from its branch to its integration, written so it can start again from any log.

Every step asks the journal first, so running this after a crash continues where the log stops.
Attempts are numbered ``<task>-a<n>``; a task has one stage, ``<task>-s``, because increment 1 has
only the implementer.
"""

from forja.core.adapters.executor import ErrorKind
from forja.core.events.state import RunState
from forja.core.gates import CheckRun, Inconclusive, Rejected, Verdict
from forja.core.states import AttemptState, Level, StageState, TaskState
from forja.orchestrator.budget import consecutive_infra_failures, quality_attempts
from forja.orchestrator.outcome import StopRun
from forja.orchestrator.ports import (
    AgentResult,
    AttemptContext,
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

    def info(self, task_id: str) -> TaskInfo:
        payload = self._state.transition_payload(Level.TASK, task_id, TaskState.PENDING) or {}
        scope = payload.get("scope")
        return TaskInfo(
            task_id,
            f"{task_id}-s",
            str(payload.get("intent", "")),
            tuple(str(p) for p in scope) if isinstance(scope, list) else (),
            _count(payload.get("max_files")),
            _count(payload.get("max_lines")),
        )

    async def run(self, task_id: str) -> None:
        ctx, journal = self._ctx, self._journal
        info = self.info(task_id)
        journal.enter(Level.TASK, task_id, TaskState.IN_PROGRESS)
        await journal.operate(
            "create_task_branch",
            Level.TASK,
            task_id,
            task_id,
            ctx.workspace.create_task_branch(task_id),
        )
        journal.enter(Level.STAGE, info.stage_id, StageState.PENDING, parent=task_id)
        journal.enter(Level.STAGE, info.stage_id, StageState.IN_PROGRESS)
        if self._state.state_of(Level.STAGE, info.stage_id) is StageState.INFRA_PAUSED:
            self._log.append_transition(
                Level.STAGE, info.stage_id, StageState.INFRA_PAUSED, StageState.IN_PROGRESS
            )
        while (attempt := self._next_attempt(info)) is not None:
            await self._attempt(info, attempt)
        await self._finish(info)

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
            self._exhaust(info, "time_budget_exhausted")
            return None
        return f"{info.task_id}-a{len(children) + 1}"

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
                reason = (payload or {}).get("reason")
                return reason if isinstance(reason, str) else None
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
            "prepare_workcopy", Level.ATTEMPT, attempt, attempt, run.agent.prepare_workcopy(ctx)
        )
        journal.enter(Level.ATTEMPT, attempt, AttemptState.WORKCOPY_READY)
        journal.enter(Level.ATTEMPT, attempt, AttemptState.AGENT_RUNNING)

        if self._state.state_of(Level.ATTEMPT, attempt) is AttemptState.AGENT_RUNNING:
            result, differences = await self._call_agent(ctx)
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
                self._reject(attempt, "git changed while the agent ran: " + "; ".join(differences))

        if self._state.state_of(Level.ATTEMPT, attempt) is AttemptState.VALIDATING:
            await self._judge(ctx)
        if self._state.state_of(Level.ATTEMPT, attempt) is AttemptState.APPROVED:
            await self._commit(ctx)

    async def _call_agent(self, ctx: AttemptContext) -> tuple[AgentResult, list[str]]:
        run = self._ctx
        op_id = self._journal.operation_id("call_agent_cli", ctx.attempt_id)
        if op_id is None:
            return AgentResult(), []  # it ended before a crash; the gates judge what it left
        async with run.workspace.watch() as watch:
            result = await run.agent.call(
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
                "apply_diff", Level.ATTEMPT, attempt, attempt, run.agent.apply_diff(ctx)
            )
        except RejectedWork as rejected:
            self._reject(attempt, str(rejected))
            return
        outcome = await run.measurer.judge(ctx, run.sinks)
        for assumption in outcome.assumptions:
            journal.note(
                "premise",
                {"task": ctx.task.task_id, "attempt": attempt, "check": assumption.check_id},
            )
        stopper = outcome.stopped_by
        if outcome.verdict is Verdict.PASSED:
            journal.enter(Level.ATTEMPT, attempt, AttemptState.APPROVED)
        elif outcome.verdict is Verdict.REJECTED and stopper is not None:
            self._reject(attempt, describe_stop(stopper))
        elif stopper is not None:
            self._block(ctx.task, attempt, describe_stop(stopper))

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
        reason = str((validating or {}).get("reason", ""))
        message = CommitMessage.refactor(
            info.intent,
            reason,
            agent=f"{run.config.implementer.name} {run.config.implementer.version}",
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
        journal.enter(Level.STAGE, info.stage_id, StageState.COMMITTED)

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
            raise StopRun("the network did not come back before the budget ran out")

    def _stage_pause(self, info: TaskInfo) -> None:
        if self._state.state_of(Level.STAGE, info.stage_id) is StageState.IN_PROGRESS:
            self._log.append_transition(
                Level.STAGE, info.stage_id, StageState.IN_PROGRESS, StageState.INFRA_PAUSED
            )

    async def _network_came_back(self) -> bool:
        run = self._ctx
        while not run.meter.exhausted():
            self._journal.note("waiting_for_network")
            await run.sleep(run.probe_interval)
            if await run.network_is_up():
                return True
        return False

    # -- the end of the task --------------------------------------------------------------------

    async def _finish(self, info: TaskInfo) -> None:
        run, journal = self._ctx, self._journal
        task = info.task_id
        stage = self._state.state_of(Level.STAGE, info.stage_id)
        if stage is StageState.EXHAUSTED:
            payload = self._state.transition_payload(
                Level.STAGE, info.stage_id, StageState.EXHAUSTED
            )
            journal.enter(Level.TASK, task, TaskState.BLOCKED, payload=payload)
            return
        if stage is not StageState.COMMITTED:
            return
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
        if outcome.verdict is Verdict.PASSED:
            journal.enter(Level.TASK, task, TaskState.INTEGRATED)
            return
        await journal.operate(
            "rollback_integration", Level.TASK, task, task, run.workspace.rollback_integration(task)
        )
        stopper = outcome.stopped_by
        journal.enter(
            Level.TASK,
            task,
            TaskState.BLOCKED,
            payload={
                "reason": "integration_gate",
                "detail": describe_stop(stopper) if stopper is not None else "",
            },
        )
