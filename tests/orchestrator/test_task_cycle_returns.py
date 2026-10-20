"""What a task's log says about its test author and about attempts sent back to it."""

from pathlib import Path
from typing import Any

from pydantic import JsonValue

from forja.core.artifacts.models import Producer
from forja.core.events import EventLog
from forja.core.states import AttemptState, Level, StageState, TaskState
from forja.orchestrator.ports import TaskInfo
from forja.orchestrator.task_cycle import TaskCycle
from tests.orchestrator.fakes import ScriptedAgent, ScriptedMeasurer, ScriptedPlanner
from tests.orchestrator.harness import RUN, MemoryWorld

STAGES: JsonValue = ["test_author", "implementer"]
UNTESTED: dict[str, JsonValue] = {"reason": "no test", "untested": ["src/a.py:3"]}


def cycle_for(tmp_path: Path) -> tuple[TaskCycle, EventLog]:
    world = MemoryWorld(tmp_path)
    _, log = world.run()
    ctx = world.context(
        log, measurer=ScriptedMeasurer(), agent=ScriptedAgent(), planner=ScriptedPlanner()
    )
    log.append_transition(
        Level.TASK,
        "x1",
        None,
        TaskState.PENDING,
        parent_id=RUN,
        payload={"stages": STAGES, "test_root": "tests"},
    )
    return TaskCycle(ctx), log


def stage(
    log: EventLog, stage_id: str, *final: tuple[StageState, dict[str, JsonValue] | None]
) -> None:
    log.append_transition(Level.STAGE, stage_id, None, StageState.PENDING, parent_id="x1")
    previous = StageState.PENDING
    for state, payload in final:
        log.append_transition(Level.STAGE, stage_id, previous, state, payload=payload)
        previous = state


def rejected(log: EventLog, stage_id: str, attempt: str, payload: dict[str, JsonValue]) -> None:
    log.append_transition(Level.ATTEMPT, attempt, None, AttemptState.CREATED, parent_id=stage_id)
    path = (
        AttemptState.WORKCOPY_READY,
        AttemptState.AGENT_RUNNING,
        AttemptState.VALIDATING,
        AttemptState.REJECTED,
    )
    previous = AttemptState.CREATED
    for state in path:
        log.append_transition(
            Level.ATTEMPT, attempt, previous, state, payload=payload if state is path[-1] else None
        )
        previous = state


def test_the_implementer_is_given_what_the_test_author_froze(tmp_path: Path) -> None:
    cycle, log = cycle_for(tmp_path)
    stage(
        log,
        "x1-t",
        (StageState.IN_PROGRESS, None),
        (StageState.COMMITTED, {"frozen_digest": "abc"}),
    )

    assert cycle.info("x1").frozen_digest == "abc"


def test_a_stage_committed_with_other_facts_froze_nothing(tmp_path: Path) -> None:
    cycle, log = cycle_for(tmp_path)
    stage(
        log,
        "x1-t",
        (StageState.IN_PROGRESS, None),
        (StageState.COMMITTED, {"other": 1}),
    )

    assert cycle.info("x1").frozen_digest == ""


def test_only_the_implementers_stage_is_sent_back_to_the_test_author(tmp_path: Path) -> None:
    cycle, log = cycle_for(tmp_path)
    stage(log, "x1-t", (StageState.IN_PROGRESS, None))
    rejected(log, "x1-t", "x1-ta1", UNTESTED)

    assert cycle._returns(cycle.info("x1", Producer.TEST_AUTHOR)) == []


def test_the_stage_waits_for_the_test_author_on_its_last_attempt_only(tmp_path: Path) -> None:
    cycle, log = cycle_for(tmp_path)
    stage(log, "x1-t", (StageState.IN_PROGRESS, None), (StageState.COMMITTED, {}))
    stage(log, "x1-s", (StageState.IN_PROGRESS, None))
    rejected(log, "x1-s", "x1-a1", UNTESTED)
    rejected(log, "x1-s", "x1-a2", UNTESTED)

    assert cycle._returned(cycle.info("x1")) == "x1-a2"


def freezing(worktree: Path, **task: Any) -> dict[str, JsonValue] | None:
    info = TaskInfo("x1", "x1-t", "x", (), 8, 400, **task)
    return TaskCycle._frozen(info, worktree)


def test_only_the_test_author_with_a_tests_root_freezes_tests(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_a.py").write_text("x = 1\n", encoding="utf-8")

    frozen = freezing(tmp_path, role=Producer.TEST_AUTHOR, test_root="tests")

    assert frozen is not None and frozen["frozen_digest"]
    assert freezing(tmp_path, role=Producer.IMPLEMENTER, test_root="tests") is None
    assert freezing(tmp_path, role=Producer.TEST_AUTHOR) is None
