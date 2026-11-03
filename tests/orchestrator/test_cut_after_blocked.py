"""A cut between the BLOCKED of a merge that does not apply and the effect that settles its intent:
the resume leaves the task blocked, settles the intent as nothing applied, and merges nothing."""

from pathlib import Path

import pytest
from pydantic import JsonValue

from forja.core.events import Event, EventLog, LogUnusable
from forja.core.states import ExecutionState, Level, TaskState
from forja.orchestrator.operations import Step
from forja.orchestrator.workspace_git import IntegrationConflict
from tests.orchestrator.crash import Counting, CrashAfter, Interrupted
from tests.orchestrator.fakes import ScriptedPlanner
from tests.orchestrator.harness import RUN, TWO_TASKS, MemoryWorld

MERGE = "integrate_task:t1"


def clashing_on_t1(world: MemoryWorld) -> list[str]:
    """Make the merge of t1 not apply, as one that clashes with what reached the run branch."""
    real = world.workspace.integrate_task
    built: list[str] = []

    def clashing(task_id: str, subject: str) -> Step:
        step: Step = real(task_id, subject)
        if task_id != "t1":
            return step
        built.append(task_id)

        async def run() -> None:
            raise IntegrationConflict(f"forja/{RUN}/t1 does not merge into the run branch")

        return Step(step.payload, run)

    world.workspace.integrate_task = clashing
    return built


def is_blocked_by_the_conflict(event: Event) -> bool:
    return (
        event.type == "transition"
        and event.level is Level.TASK
        and event.target_id == "t1"
        and event.to_state == "blocked"
    )


def lines_until_blocked(root: Path) -> int:
    """How many lines an uninterrupted run has written when t1 is blocked by the conflict."""
    counter, found = Counting(), list[int]()
    reference = MemoryWorld(root)
    clashing_on_t1(reference)
    log = reference.open(write=counter)
    log.subscribe(
        lambda e: (
            found.append(counter.count) if is_blocked_by_the_conflict(e) and not found else None
        )
    )
    reference.run(log=log, planner=ScriptedPlanner(TWO_TASKS))
    return found[0]


def settled_effect(log: EventLog) -> dict[str, JsonValue] | None:
    return log.state.effect_of(MERGE)


def test_a_cut_after_the_block_and_before_the_effect_leaves_the_task_blocked_and_the_merge_settled(
    tmp_path: Path,
) -> None:
    cut = lines_until_blocked(tmp_path / "reference")
    world = MemoryWorld(tmp_path / "world")
    built = clashing_on_t1(world)
    with pytest.raises((Interrupted, LogUnusable)):
        world.run(log=world.open(write=CrashAfter(cut)), planner=ScriptedPlanner(TWO_TASKS))
    cut_log = world.open()
    assert cut_log.state.state_of(Level.TASK, "t1") is TaskState.BLOCKED  # the cut is where wanted
    assert MERGE in cut_log.state.open_operations
    assert settled_effect(cut_log) is None
    cut_log.close()

    outcome, log = world.run(log=world.open(), planner=ScriptedPlanner(TWO_TASKS))

    assert outcome.state is ExecutionState.DELIVERED
    assert log.state.state_of(Level.TASK, "t1") is TaskState.BLOCKED
    blocked = log.state.transition_payload(Level.TASK, "t1", TaskState.BLOCKED)
    assert blocked is not None and blocked["reason"] == "integration_conflict"
    assert log.state.state_of(Level.TASK, "t2") is TaskState.INTEGRATED
    assert log.state.open_operations == {}
    assert settled_effect(log) is not None  # nothing applied, and the log says so
    assert built == ["t1"]  # the resume did not try the merge again
    memory = world.memory
    subjects = [c.subject for c in memory.log(world.workspace.run_branch)]
    assert "merge: reduce the complexity of f" not in subjects
    assert "merge: reduce the complexity of g" in subjects
    assert "src/t1.py" not in memory.tip(world.workspace.run_branch).tree
    assert memory.branches["main"] == memory.base
