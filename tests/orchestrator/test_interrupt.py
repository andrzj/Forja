"""A person stops the run: it is saved where it was, nothing is counted against the task, and the
next ``forja`` resumes to the same end."""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from forja.core.events import EventLog
from forja.core.states import AttemptState, ExecutionState, Level, StageState, TaskState
from forja.orchestrator.budget import consecutive_infra_failures, quality_attempts
from forja.orchestrator.outcome import ExitCode
from forja.orchestrator.phases import Orchestrator, confirm_run
from forja.orchestrator.ports import AgentResult, AttemptContext, SinkFactory
from tests.orchestrator.fakes import ScriptedAgent, ScriptedMeasurer, ScriptedPlanner
from tests.orchestrator.harness import ISOLATION, RUN, MemoryWorld


@dataclass
class Waiting(ScriptedAgent):
    """An agent that is in the middle of its call until the test says so."""

    started: asyncio.Event | None = None

    async def call(self, ctx: AttemptContext, operation_id: str, sink: Any) -> AgentResult:
        assert self.started is not None
        self.started.set()
        await asyncio.sleep(3600)
        raise AssertionError("the call should have been cancelled")


class SlowJudge(ScriptedMeasurer):
    started: asyncio.Event | None = None

    async def judge(self, ctx: AttemptContext, sinks: SinkFactory) -> Any:
        assert self.started is not None
        self.started.set()
        await asyncio.sleep(3600)
        raise AssertionError("the judgment should have been cancelled")


def stop_when(world: MemoryWorld, log: EventLog, make: Callable[[asyncio.Event], Any]) -> None:
    """Run until the part made by ``make`` says it has started, then cancel like Ctrl+K."""

    async def scenario() -> None:
        started = asyncio.Event()
        agent, measurer = make(started)
        ctx = world.context(log, measurer=measurer, agent=agent, planner=ScriptedPlanner())
        task = asyncio.create_task(Orchestrator(ctx).run())
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(scenario())


def in_the_agent(started: asyncio.Event) -> tuple[Any, Any]:
    return Waiting(started=started), ScriptedMeasurer()


def in_the_judgment(started: asyncio.Event) -> tuple[Any, Any]:
    measurer = SlowJudge()
    measurer.started = started
    return ScriptedAgent(), measurer


def attempts_of(log: EventLog) -> dict[str, AttemptState]:
    found = {}
    for task in log.state.children_of(Level.TASK, RUN):
        for stage in log.state.children_of(Level.STAGE, task):
            for attempt in log.state.children_of(Level.ATTEMPT, stage):
                state = log.state.state_of(Level.ATTEMPT, attempt)
                assert isinstance(state, AttemptState)
                found[attempt] = state
    return found


def stopped(tmp_path: Path, make: Callable[[asyncio.Event], Any]) -> tuple[MemoryWorld, EventLog]:
    world = MemoryWorld(tmp_path)
    log = world.open()
    confirm_run(log, world.config, ISOLATION)
    stop_when(world, log, make)
    return world, log


def test_stopping_during_the_agent_pauses_the_run_and_drops_the_attempt_without_counting_it(
    tmp_path: Path,
) -> None:
    _, log = stopped(tmp_path, in_the_agent)

    state = log.state
    assert state.state_of(Level.EXECUTION, RUN) is ExecutionState.PAUSED
    assert state.transition_payload(Level.EXECUTION, RUN, ExecutionState.PAUSED) == {
        "reason": "interrupted"
    }
    assert attempts_of(log) == {"t1-a1": AttemptState.DISCARDED}
    assert quality_attempts(state, "t1-s") == 0
    assert consecutive_infra_failures(state, "t1-s") == 0
    assert b'"reason":"interrupted"' in log.path.read_bytes()


def test_the_run_that_was_stopped_in_the_agent_resumes_to_the_same_end(tmp_path: Path) -> None:
    world, _ = stopped(tmp_path, in_the_agent)

    outcome, log = world.run(log=world.open())

    assert outcome.exit_code is ExitCode.DELIVERED
    assert log.state.state_of(Level.TASK, "t1") is TaskState.INTEGRATED
    assert log.state.state_of(Level.STAGE, "t1-s") is StageState.COMMITTED
    attempts = attempts_of(log)
    assert attempts["t1-a1"] is AttemptState.DISCARDED
    assert AttemptState.COMMITTED in attempts.values()
    assert quality_attempts(log.state, "t1-s") == 1


def test_stopping_during_the_judgment_resumes_too(tmp_path: Path) -> None:
    world, log = stopped(tmp_path, in_the_judgment)

    assert log.state.state_of(Level.EXECUTION, RUN) is ExecutionState.PAUSED
    outcome, log = world.run(log=world.open())
    assert outcome.exit_code is ExitCode.DELIVERED
    assert log.state.open_operations == {}


def test_a_run_that_was_already_delivered_is_not_paused_by_a_late_cancel(tmp_path: Path) -> None:
    world = MemoryWorld(tmp_path)
    outcome, log = world.run()
    assert outcome.exit_code is ExitCode.DELIVERED
    ctx = world.context(
        log, measurer=ScriptedMeasurer(), agent=ScriptedAgent(), planner=ScriptedPlanner()
    )

    Orchestrator(ctx)._interrupted()  # noqa: SLF001

    assert log.state.state_of(Level.EXECUTION, RUN) is ExecutionState.DELIVERED
