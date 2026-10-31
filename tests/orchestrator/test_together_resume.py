"""Tasks that ran together and were cut: the resume puts them back, and the summary keeps the
order of the log, not the order in which they finished."""

import asyncio
from dataclasses import dataclass
from pathlib import Path

import pytest

from forja.core.states import ExecutionState, Level, TaskState
from forja.orchestrator.config import RunConfig
from forja.orchestrator.ports import AttemptContext
from tests.orchestrator.fakes import AgentResult, ScriptedAgent, ScriptedPlanner
from tests.orchestrator.harness import MemoryWorld
from tests.orchestrator.test_together import APART, Watched


@dataclass
class Slow(ScriptedAgent):
    """The first task takes longer than the second, so the second finishes first."""

    async def call(self, ctx: AttemptContext, operation_id: str, sink: object) -> AgentResult:
        await asyncio.sleep(0.3 if ctx.task.task_id == "t1" else 0.01)
        return await super().call(ctx, operation_id, sink)  # type: ignore[arg-type]


@dataclass
class Cut(ScriptedAgent):
    """The first task fails while the second still works: the run is cut with both open."""

    async def call(self, ctx: AttemptContext, operation_id: str, sink: object) -> AgentResult:
        if ctx.task.task_id == "t1":
            await asyncio.sleep(0.05)
            raise RuntimeError("the service fell over")
        await asyncio.sleep(30)
        return await super().call(ctx, operation_id, sink)  # type: ignore[arg-type]


@pytest.fixture
def world(tmp_path: Path) -> MemoryWorld:
    return MemoryWorld(tmp_path)


def config(world: MemoryWorld) -> RunConfig:
    return world.config.model_copy(update={"parallel_tasks": 2})


def test_a_run_cut_with_two_tasks_in_progress_puts_both_back_on_the_resume(
    world: MemoryWorld,
) -> None:
    with pytest.raises(RuntimeError, match="fell over"):
        world.run(agent=Cut(), planner=ScriptedPlanner(APART), config=config(world))
    log = world.open()
    assert {log.state.state_of(Level.TASK, t) for t in ("t1", "t2")} == {TaskState.IN_PROGRESS}
    log.close()
    again = Watched(meet=2)

    outcome, log = world.run(agent=again, planner=ScriptedPlanner(APART), config=config(world))

    assert outcome.state is ExecutionState.DELIVERED
    assert [log.state.state_of(Level.TASK, t) for t in ("t1", "t2")] == [TaskState.INTEGRATED] * 2
    assert again.most == 2  # both came back at once, not one after the other


def test_the_summary_lists_the_tasks_in_the_order_of_the_log_not_of_their_end(
    world: MemoryWorld,
) -> None:
    outcome, log = world.run(agent=Slow(), planner=ScriptedPlanner(APART), config=config(world))

    assert outcome.state is ExecutionState.DELIVERED
    integrations = [
        e for e in log.path.read_text(encoding="utf-8").splitlines() if '"integrated"' in e
    ]
    assert '"t2"' in integrations[0]  # t2 really finished first
    summary = (world.run_dir / "resumo.md").read_text(encoding="utf-8")
    assert summary.index("`t1`") < summary.index("`t2`")
