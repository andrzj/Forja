"""A fix task has two stages, the test author's and then the implementer's, in one task."""

from pathlib import Path

import pytest

from forja.checks.freeze import frozen_digest_of
from forja.core.artifacts.llm_output import DeclaredTest
from forja.core.artifacts.models import Producer
from forja.core.events import EventLog
from forja.core.states import AttemptState, ExecutionState, Level, StageState, TaskState
from forja.orchestrator.config import Budget, ExecutorRef, FixRequest, Objective
from forja.orchestrator.planner import FixPlanner
from forja.orchestrator.ports import Expectations, PlannedTask
from tests.orchestrator.fakes import (
    PASSED,
    REJECTED,
    ScriptedAgent,
    ScriptedMeasurer,
    ScriptedPlanner,
)
from tests.orchestrator.harness import MemoryWorld

FIX = FixRequest.model_validate(
    {
        "description": "page 1 is wrong",
        "criteria": {
            "criteria": [
                {"id": 1, "text": "page 1 is the first items", "level": "unit", "origin": "x"}
            ]
        },
    }
)
TASK = PlannedTask(
    "page 1 is wrong",
    ("src/a.py",),
    8,
    400,
    stages=(Producer.TEST_AUTHOR, Producer.IMPLEMENTER),
    test_root="tests",
)
TESTS = {"tests/test_a.py": "def test_a():\n    assert False\n"}
CODE = {"src/a.py": "def f():\n    return 1\n"}


@pytest.fixture
def world(tmp_path: Path) -> MemoryWorld:
    found = MemoryWorld(tmp_path)
    found.config = found.config.model_copy(
        update={
            "objective": Objective.FIX,
            "fix": FIX,
            "test_author": ExecutorRef(name="author-cli", path="/bin/author", version="2.0"),
        }
    )
    return found


def state_of(log: EventLog, level: Level, target: str) -> object:
    return log.state.state_of(level, target)


def test_the_tests_come_first_and_the_fix_after_them_in_one_task(world: MemoryWorld) -> None:
    author, implementer = ScriptedAgent(edits=[TESTS]), ScriptedAgent(edits=[CODE])

    outcome, log = world.run(
        measurer=ScriptedMeasurer(),
        agent=implementer,
        agents={Producer.TEST_AUTHOR: author},
        planner=ScriptedPlanner((TASK,)),
    )

    assert outcome.state is ExecutionState.DELIVERED
    assert state_of(log, Level.TASK, "t1") is TaskState.INTEGRATED
    assert state_of(log, Level.STAGE, "t1-t") is StageState.COMMITTED
    assert state_of(log, Level.STAGE, "t1-s") is StageState.COMMITTED
    assert state_of(log, Level.ATTEMPT, "t1-ta1") is AttemptState.COMMITTED
    assert state_of(log, Level.ATTEMPT, "t1-a1") is AttemptState.COMMITTED
    assert [c.task.role for c in author.seen] == [Producer.TEST_AUTHOR]
    assert [c.task.role for c in implementer.seen] == [Producer.IMPLEMENTER]
    memory = world.memory
    reachable = [
        memory.commits[sha] for sha in memory.ancestors(memory.tip(world.workspace.run_branch).sha)
    ]
    tests = next(c for c in reachable if c.subject.startswith("test: "))
    fix = next(c for c in reachable if c.subject.startswith("fix: "))
    assert memory.is_ancestor(tests.sha, fix.sha)
    assert tests.trailer("Agent") == ["author-cli 2.0"]
    assert fix.trailer("Agent") == ["fake-cli 1.0"]


def test_each_stage_has_its_own_attempts(world: MemoryWorld) -> None:
    measurer = ScriptedMeasurer(verdicts=(REJECTED, PASSED, REJECTED, REJECTED, PASSED))
    author, implementer = ScriptedAgent(edits=[TESTS]), ScriptedAgent(edits=[CODE])

    outcome, log = world.run(
        measurer=measurer,
        agent=implementer,
        agents={Producer.TEST_AUTHOR: author},
        planner=ScriptedPlanner((TASK,)),
        budget=Budget(attempts_per_task=3),
    )

    assert outcome.state is ExecutionState.DELIVERED
    assert log.state.children_of(Level.ATTEMPT, "t1-t") == ["t1-ta1", "t1-ta2"]
    assert log.state.children_of(Level.ATTEMPT, "t1-s") == ["t1-a1", "t1-a2", "t1-a3"]


def test_a_task_whose_tests_were_never_accepted_does_not_reach_the_implementer(
    world: MemoryWorld,
) -> None:
    author, implementer = ScriptedAgent(edits=[TESTS]), ScriptedAgent(edits=[CODE])

    _, log = world.run(
        measurer=ScriptedMeasurer(verdicts=(REJECTED,)),
        agent=implementer,
        agents={Producer.TEST_AUTHOR: author},
        planner=ScriptedPlanner((TASK,)),
        budget=Budget(attempts_per_task=2),
    )

    assert state_of(log, Level.TASK, "t1") is TaskState.BLOCKED
    assert state_of(log, Level.STAGE, "t1-t") is StageState.EXHAUSTED
    assert implementer.seen == []


def test_the_fix_planner_makes_one_task_with_the_tests_first() -> None:
    import asyncio

    from forja.orchestrator.ports import Baseline

    planned = asyncio.run(
        FixPlanner(FIX, ("src",)).plan(Path("."), Baseline(True), Budget(files_per_task=4))
    )

    assert planned == [
        PlannedTask(
            "page 1 is wrong\n\nCriteria:\n1. page 1 is the first items",
            ("src",),
            4,
            Budget().lines_per_task,
            stages=(Producer.TEST_AUTHOR, Producer.IMPLEMENTER),
            test_root="tests",
        )
    ]


def test_only_the_test_author_is_judged_against_the_criteria_it_declared_tests_for(
    world: MemoryWorld,
) -> None:
    declared = (
        DeclaredTest(criterion_id=1, test_id="tests/test_a.py::test_a", path="tests/test_a.py"),
    )
    author = ScriptedAgent(edits=[TESTS], tests=declared)
    measurer = ScriptedMeasurer()

    world.run(
        measurer=measurer,
        agent=ScriptedAgent(edits=[CODE]),
        agents={Producer.TEST_AUTHOR: author},
        planner=ScriptedPlanner((TASK,)),
    )

    assert measurer.expected == [Expectations(frozenset({1}), declared), None]


def test_the_implementer_is_told_what_the_test_author_froze(
    world: MemoryWorld, tmp_path: Path
) -> None:
    author, implementer = ScriptedAgent(edits=[TESTS]), ScriptedAgent(edits=[CODE])

    world.run(
        measurer=ScriptedMeasurer(),
        agent=implementer,
        agents={Producer.TEST_AUTHOR: author},
        planner=ScriptedPlanner((TASK,)),
    )

    first, second = author.seen[0].task, implementer.seen[0].task
    assert first.frozen_digest == ""
    assert second.frozen_digest
    for name, text in TESTS.items():
        (tmp_path / "expected" / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / "expected" / name).write_text(text, encoding="utf-8")
    assert second.frozen_digest == frozen_digest_of(tmp_path / "expected", "tests", ())
