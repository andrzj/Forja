"""One task from its branch to its integration, written so it can start again from any log.

Every step asks the journal first, so running this after a crash continues where the log stops.
The implementer's attempts are numbered ``<task>-a<n>`` and its stage is ``<task>-s``. A fix task
has the test author first, with stage ``<task>-t`` and attempts ``<task>-ta<n>``; the task joins the
run only after its last stage is committed.

An implementer attempt that the mutation gate rejects only because new lines have no test is kept
in a commit and sent to an extra test author stage, ``<task>-t<n>`` (n from 2) with attempts
``<task>-t<n>a<k>``. That stage judges the committed code and the new tests together, mutation
included; once it commits, the implementer's stage is committed with it.
"""

from dataclasses import replace
from pathlib import Path

from pydantic import JsonValue

from forja.checks.change_record import record_path
from forja.checks.freeze import frozen_digest_of
from forja.checks.readme import README_NAMES
from forja.core.adapters.executor import ErrorKind
from forja.core.artifacts.elements import elements_of
from forja.core.artifacts.models import ArtifactType, Executor, Producer
from forja.core.artifacts.schemas import CriteriaBody
from forja.core.events.state import RunState
from forja.core.gates import Approved, CheckRun, FindingKind, Inconclusive, Rejected, Verdict
from forja.core.states import AttemptState, Level, StageState, TaskState
from forja.orchestrator.budget import consecutive_infra_failures, quality_attempts
from forja.orchestrator.config import Objective
from forja.orchestrator.criteria import (
    criteria_artifact_id,
    criteria_of,
    manifest_artifact_id,
    manifest_of,
    with_criteria,
)
from forja.orchestrator.outcome import StopRun
from forja.orchestrator.ports import (
    AgentResult,
    AttemptContext,
    Expectations,
    RejectedWork,
    RunContext,
    TaskInfo,
)
from forja.orchestrator.summary import DOCUMENTATION, TRACE
from forja.orchestrator.workspace_git import CommitMessage

REASON_LIMIT = 1500
UNTESTED_LIMIT = 200
RETURNED = (
    "Returned to the test author: the new code has lines no test runs. Write tests for them; "
)
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


def untested_targets(run: CheckRun) -> list[str]:
    """Where the new code has no test, if that is the only thing the check found."""
    result = run.result
    if not isinstance(result, Rejected):
        return []
    if any(finding.kind is not FindingKind.UNTESTED_LINE for finding in result.findings):
        return []
    return [finding.target for finding in result.findings][:UNTESTED_LIMIT]


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
        letter = {Producer.TEST_AUTHOR: "t", Producer.DOCUMENTER: "d", Producer.SPECIFIER: "c"}.get(
            role, "s"
        )
        prefix = {
            Producer.TEST_AUTHOR: "ta",
            Producer.DOCUMENTER: "da",
            Producer.SPECIFIER: "ca",
        }.get(role, "a")
        test_root = str(payload.get("test_root", ""))
        return TaskInfo(
            task_id,
            f"{task_id}-{letter}",
            self._intent(task_id, role, str(payload.get("intent", ""))),
            tuple(str(p) for p in scope) if isinstance(scope, list) else (),
            _count(payload.get("max_files")),
            _count(payload.get("max_lines")),
            role,
            test_root,
            f"{task_id}-{prefix}",
            "" if author else self._frozen_digest(task_id),
        )

    def _intent(self, task_id: str, role: Producer, planned: str) -> str:
        """What the stage is told to do. The stages after the specifier get the criteria it wrote
        added to the plan's intent, which could not have them when it was made."""
        if role is Producer.SPECIFIER or Producer.SPECIFIER not in self.roles(task_id):
            return planned
        if self._state.state_of(Level.STAGE, f"{task_id}-c") is not StageState.COMMITTED:
            return planned
        criteria = criteria_of(self._ctx, task_id)
        return planned if criteria is None else with_criteria(planned, criteria)

    def _frozen_digest(self, task_id: str) -> str:
        """What the test author's stage froze, read from its commit; empty if it had none."""
        if Producer.TEST_AUTHOR not in self.roles(task_id):
            return ""
        if not self._state.has_target(Level.STAGE, f"{task_id}-t"):
            return ""  # a stage before the test author's asks, and it has frozen nothing yet
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
        returned = self._returned(info)
        if returned is not None:
            return await self._rework(info, returned)
        stage = self._state.state_of(Level.STAGE, info.stage_id)
        if stage is StageState.EXHAUSTED and not info.reviews:
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
        if self._returned(info) is not None:
            return None
        budget = self._ctx.config.budget
        if quality_attempts(state, info.stage_id) >= budget.attempts_per_task:
            self._exhaust(info, "attempts_exhausted")
            return None
        if self._ctx.meter.exhausted():
            self._exhaust(info, "token_budget_exhausted")
            return None
        return f"{info.attempt_prefix}{len(children) + 1}"

    def _exhaust(self, info: TaskInfo, reason: str, **details: JsonValue) -> None:
        self._log.append_transition(
            Level.STAGE,
            info.stage_id,
            StageState.IN_PROGRESS,
            StageState.EXHAUSTED,
            payload={"reason": reason, **details},
        )

    # -- the return to the test author ----------------------------------------------------------

    def _untested_by(self, attempt: str) -> list[JsonValue]:
        """The places a rejected attempt left without a test; empty if it was rejected otherwise."""
        payload = self._state.transition_payload(Level.ATTEMPT, attempt, AttemptState.REJECTED)
        found = payload.get("untested") if payload else None
        return found if isinstance(found, list) else []

    def _returns(self, info: TaskInfo) -> list[str]:
        """The attempts of an implementer stage that went back to the test author, in order."""
        if info.role is not Producer.IMPLEMENTER or info.reviews:
            return []
        attempts = self._state.children_of(Level.ATTEMPT, info.stage_id)
        return [a for a in attempts if self._untested_by(a)]

    def _returned(self, info: TaskInfo) -> str | None:
        """The attempt the stage is waiting on the test author for, if it is."""
        if self._state.state_of(Level.STAGE, info.stage_id) is not StageState.IN_PROGRESS:
            return None
        returns = self._returns(info)
        last = self._state.children_of(Level.ATTEMPT, info.stage_id)[-1:]
        return returns[-1] if returns and last == returns[-1:] else None

    def rework_info(self, info: TaskInfo, attempt: str) -> TaskInfo:
        """The extra test author stage for the ``attempt`` of the implementer's ``info``."""
        number = self._returns(info).index(attempt) + 2
        author = self.info(info.task_id, Producer.TEST_AUTHOR)
        return replace(
            author,
            stage_id=f"{info.task_id}-t{number}",
            attempt_prefix=f"{info.task_id}-t{number}a",
            test_root=author.test_root or self._ctx.test_root,
            reviews=info.stage_id,
        )

    async def _rework(self, info: TaskInfo, attempt: str) -> bool:
        """The test author writes what the new code lacks; the implementer's stage ends with it."""
        extra = self.rework_info(info, attempt)
        if await self._stage(extra):
            self._journal.enter(Level.STAGE, info.stage_id, StageState.COMMITTED)
            return True
        gone = self._state.transition_payload(Level.STAGE, extra.stage_id, StageState.EXHAUSTED)
        detail = self._own_rejection(extra) or str(gone)
        if self._state.state_of(Level.STAGE, info.stage_id) is StageState.IN_PROGRESS:
            self._exhaust(
                info,
                "tests_for_new_lines_exhausted",
                detail=detail[:REASON_LIMIT],
                lines=self._untested_by(attempt),
            )
        payload = self._state.transition_payload(Level.STAGE, info.stage_id, StageState.EXHAUSTED)
        self._journal.enter(Level.TASK, info.task_id, TaskState.BLOCKED, payload=payload)
        return False

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
                payload=await self._frozen(info, ctx.workspace.attempt_worktree(attempt)),
            )
        elif self._untested_by(attempt):
            await self._commit_attempt(info, attempt)
        await journal.operate(
            "remove_worktree",
            Level.ATTEMPT,
            attempt,
            attempt,
            ctx.workspace.remove_worktree(attempt),
        )

    def _own_rejection(self, info: TaskInfo) -> str | None:
        state = self._state
        for attempt in reversed(state.children_of(Level.ATTEMPT, info.stage_id)):
            if state.state_of(Level.ATTEMPT, attempt) is AttemptState.REJECTED:
                payload = state.transition_payload(Level.ATTEMPT, attempt, AttemptState.REJECTED)
                assert payload is not None  # _reject always says why
                return str(payload["reason"])
        return None

    def _last_rejection(self, info: TaskInfo) -> str | None:
        """Why the stage's last attempt was rejected. An extra test stage starts from the reason
        the implementer's attempt was sent back to it."""
        own = self._own_rejection(info)
        if own is not None or not info.reviews:
            return own
        return f"{RETURNED}{self._own_rejection(self.info(info.task_id))}"[:REASON_LIMIT]

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
        if ctx.task.role is Producer.DOCUMENTER:
            ctx = replace(
                ctx,
                readme=await run.measurer.readme_report(ctx),
                adr=await run.measurer.adr_report(ctx),
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

    def _reject(self, attempt: str, reason: str, untested: list[str] | None = None) -> None:
        payload: dict[str, JsonValue] = {"reason": reason[:REASON_LIMIT]}
        if untested:
            payload["untested"] = [*untested]
        self._log.append_transition(
            Level.ATTEMPT,
            attempt,
            self._state.state_of(Level.ATTEMPT, attempt),
            AttemptState.REJECTED,
            payload=payload,
        )

    async def _judge(self, ctx: AttemptContext) -> None:
        run, journal = self._ctx, self._journal
        attempt = ctx.attempt_id
        validating = self._state.transition_payload(Level.ATTEMPT, attempt, AttemptState.VALIDATING)
        ctx = replace(ctx, message=str(validating.get("reason", "")) if validating else "")
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
        if ctx.task.role is Producer.DOCUMENTER:
            await self._write_record(ctx)
        outcome = await run.measurer.judge(ctx, run.sinks, self._expectations(ctx))
        for assumption in outcome.assumptions:
            journal.note(
                "premise",
                {"task": ctx.task.task_id, "attempt": attempt, "check": assumption.check_id},
            )
        stopper = outcome.stopped_by
        if stopper is None:
            if ctx.task.role is Producer.SPECIFIER:
                self._record_criteria(ctx)
            if ctx.task.role is Producer.TEST_AUTHOR and not ctx.task.reviews:
                self._record_manifest(ctx)
            passed: list[JsonValue] = [
                r.check_id for r in outcome.runs if isinstance(r.result, Approved)
            ]
            journal.enter(
                Level.ATTEMPT, attempt, AttemptState.APPROVED, payload={"gates_passed": passed}
            )
            if ctx.task.role is Producer.DOCUMENTER:
                journal.note(
                    DOCUMENTATION,
                    {
                        "task": ctx.task.task_id,
                        "record": record_path(ctx.task.task_id),
                        "files": [*await run.measurer.documents(ctx)],
                    },
                )
        elif outcome.verdict is Verdict.REJECTED:
            untested = untested_targets(stopper)
            sent_back = bool(untested) and ctx.task.role is Producer.IMPLEMENTER
            self._reject(attempt, describe_stop(stopper), untested if sent_back else None)
            if sent_back:
                await self._commit_attempt(ctx.task, attempt)
        else:
            self._block(ctx.task, attempt, describe_stop(stopper))

    def _record_criteria(self, ctx: AttemptContext) -> None:
        """The Forja writes the criteria the specifier declared as an artifact of the run, with the
        elements it left out as assumptions; the specifier never writes a file."""
        run = self._ctx
        output = run.runner(ctx.task.role).declared_output(ctx)
        executor = run.config.implementer
        run.store.put(
            artifact_type=ArtifactType.CRITERIA,
            producer=Producer.SPECIFIER,
            body=CriteriaBody(criteria=output.criteria),
            executor=Executor(cli=executor.name, version=executor.version),
            attempt_id=ctx.attempt_id,
            assumptions=(*output.assumptions, *(item.as_assumption() for item in output.left_out)),
            artifact_id=criteria_artifact_id(ctx.task.task_id),
        )

    def _record_manifest(self, ctx: AttemptContext) -> None:
        """The Forja writes the manifest of the tests the author declared (which test covers which
        criterion, and its seeded data generators) and notes the trace for the summary."""
        run = self._ctx
        criteria = criteria_of(run, ctx.task.task_id)
        if criteria is None:  # a refactoring has no test author
            return
        output = run.runner(ctx.task.role).declared_output(ctx)
        if not output.tests:  # apply_diff refuses that; only a scripted agent gets here
            return
        manifest = manifest_of(output)
        executor = run.config.test_author or run.config.implementer
        run.store.put(
            artifact_type=ArtifactType.TEST_MANIFEST,
            producer=Producer.TEST_AUTHOR,
            body=manifest,
            executor=Executor(cli=executor.name, version=executor.version),
            attempt_id=ctx.attempt_id,
            assumptions=output.assumptions,
            artifact_id=manifest_artifact_id(ctx.task.task_id),
        )
        self._journal.note(
            TRACE,
            {
                "task": ctx.task.task_id,
                "criteria": [
                    {
                        "id": c.id,
                        "text": c.text,
                        "origin": [*c.origin],
                        "tests": [t.test_id for t in manifest.tests if t.criterion_id == c.id],
                    }
                    for c in criteria.criteria
                ],
            },
        )

    async def _write_record(self, ctx: AttemptContext) -> None:
        """The Forja writes the change record itself, from the facts it measured and the claims
        the documenter made: the agent never writes it, so it can never change a fact."""
        run = self._ctx
        record = await run.measurer.change_record(
            ctx,
            run.sinks,
            run.runner(ctx.task.role).declared_claims(ctx),
            self._gates_passed(ctx.task.task_id),
            self._executors(),
        )
        target = ctx.worktree / record.path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(record.text, encoding="utf-8", newline="\n")

    def _gates_passed(self, task_id: str) -> list[str]:
        """The gates the task's committed attempts passed, in the order they first passed."""
        passed: dict[str, None] = {}
        for stage in self._state.children_of(Level.STAGE, task_id):
            for attempt in self._state.children_of(Level.ATTEMPT, stage):
                if self._state.state_of(Level.ATTEMPT, attempt) is not AttemptState.COMMITTED:
                    continue
                payload = self._state.transition_payload(
                    Level.ATTEMPT, attempt, AttemptState.APPROVED
                )
                found = payload.get("gates_passed") if payload else None
                if isinstance(found, list):
                    passed.update(dict.fromkeys(str(g) for g in found))
        return list(passed)

    def _executors(self) -> list[Executor]:
        config = self._ctx.config
        refs = [config.implementer, *([config.test_author] if config.test_author else [])]
        return list(dict.fromkeys(Executor(cli=ref.name, version=ref.version) for ref in refs))

    def _expectations(self, ctx: AttemptContext) -> Expectations | None:
        if ctx.task.role is Producer.DOCUMENTER:
            claims = self._ctx.runner(ctx.task.role).declared_claims(ctx)
            return Expectations(frozenset(), (), claims)
        if ctx.task.role is Producer.SPECIFIER:
            output = self._ctx.runner(ctx.task.role).declared_output(ctx)
            elements = elements_of(ctx.task.intent)
            return Expectations(
                frozenset(), (), output.claims, elements, output.criteria, output.left_out
            )
        if ctx.task.role is not Producer.TEST_AUTHOR or ctx.task.reviews:
            return None
        criteria = criteria_of(self._ctx, ctx.task.task_id)
        if criteria is None:
            return None
        output = self._ctx.runner(ctx.task.role).declared_output(ctx)
        declared = output.tests  # apply_diff already refused tests that make no manifest
        return Expectations(frozenset(int(c.id) for c in criteria.criteria), declared)

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

    def _commit_message(self, info: TaskInfo, attempt: str, kind: str = "") -> CommitMessage:
        run = self._ctx
        validating = self._state.transition_payload(Level.ATTEMPT, attempt, AttemptState.VALIDATING)
        assert validating is not None  # _work records the agent's reason on the way in
        author = info.role is Producer.TEST_AUTHOR
        executor = (
            (run.config.test_author or run.config.implementer)
            if author
            else (run.config.implementer)
        )
        kind = kind or (
            "docs"
            if info.role is Producer.DOCUMENTER
            else "test"
            if author
            else "fix"
            if run.config.objective is Objective.FIX
            else "refactor"
        )
        return CommitMessage.of(
            kind,
            info.intent,
            str(validating["reason"]),
            agent=f"{executor.name} {executor.version}",
            policy_version=run.config.policy_version,
        )

    async def _commit_attempt(self, info: TaskInfo, attempt: str) -> None:
        """Also what keeps the work of an attempt sent back to the test author, so it sees it."""
        apart: list[str] = []
        if info.role is Producer.DOCUMENTER:  # the README gets a commit of its own
            worktree = self._ctx.workspace.attempt_worktree(attempt)
            apart = [name for name in README_NAMES if (worktree / name).is_file()]
        await self._journal.operate(
            "commit_stage",
            Level.ATTEMPT,
            attempt,
            attempt,
            self._ctx.workspace.commit_stage(
                info.task_id,
                info.stage_id,
                attempt,
                self._commit_message(info, attempt),
                apart,
                self._commit_message(info, attempt, "docs(readme)") if apart else None,
            ),
        )

    async def _commit(self, ctx: AttemptContext) -> None:
        journal = self._journal
        attempt, info = ctx.attempt_id, ctx.task
        if info.role is not Producer.SPECIFIER:  # the specifier changes nothing: no commit
            await self._commit_attempt(info, attempt)
        journal.enter(Level.ATTEMPT, attempt, AttemptState.COMMITTED)
        journal.enter(
            Level.STAGE,
            info.stage_id,
            StageState.COMMITTED,
            payload=await self._frozen(info, ctx.worktree),
        )

    async def _frozen(self, info: TaskInfo, worktree: Path) -> dict[str, JsonValue] | None:
        """The test author freezes its tests; the implementer must leave them as they are."""
        if info.role is not Producer.TEST_AUTHOR:
            return None
        tests = await self._ctx.test_files(worktree)
        return {"frozen_digest": frozen_digest_of(worktree, info.test_root, tests)}

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
