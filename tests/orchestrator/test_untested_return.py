"""New code no test runs goes back to the test author, and only then to the mutation again."""

from pathlib import Path

import pytest

from forja.core.artifacts.models import Producer
from forja.core.events import EventLog
from forja.core.gates import PipelineOutcome
from forja.core.states import AttemptState, ExecutionState, Level, StageState, TaskState
from forja.orchestrator.config import Budget, ExecutorRef, FixRequest, Objective
from forja.orchestrator.ports import AttemptContext, PlannedTask, SinkFactory
from tests.orchestrator.fakes import (
    PASSED,
    REJECTED,
    UNTESTED,
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
MORE_TESTS = {"tests/test_b.py": "def test_b():\n    assert True\n"}
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


def run(
    world: MemoryWorld,
    measurer: ScriptedMeasurer,
    author: ScriptedAgent,
    budget: Budget | None = None,
) -> tuple[ExecutionState, EventLog, ScriptedAgent]:
    implementer = ScriptedAgent(edits=[CODE])
    outcome, log = world.run(
        measurer=measurer,
        agent=implementer,
        agents={Producer.TEST_AUTHOR: author},
        planner=ScriptedPlanner((TASK,)),
        budget=budget,
    )
    return outcome.state, log, implementer


class ByRole(ScriptedMeasurer):
    """The implementer is always told its lines have no test; the test author is always approved."""

    async def judge(
        self, ctx: AttemptContext, sinks: SinkFactory, expectations: object = None
    ) -> PipelineOutcome:
        self.judged.append(ctx.attempt_id)
        return UNTESTED if ctx.task.role is Producer.IMPLEMENTER else PASSED


def test_a_line_without_a_test_goes_to_the_test_author_and_the_task_goes_on(
    world: MemoryWorld,
) -> None:
    author = ScriptedAgent(edits=[TESTS, MORE_TESTS])
    measurer = ScriptedMeasurer(verdicts=(PASSED, UNTESTED, PASSED))

    state, log, implementer = run(world, measurer, author)

    assert state is ExecutionState.DELIVERED
    assert state_of(log, Level.TASK, "t1") is TaskState.INTEGRATED
    assert measurer.judged == ["t1-ta1", "t1-a1", "t1-t2a1"]
    assert log.state.children_of(Level.STAGE, "t1") == ["t1-t", "t1-s", "t1-t2"]
    assert state_of(log, Level.STAGE, "t1-t2") is StageState.COMMITTED
    assert state_of(log, Level.STAGE, "t1-s") is StageState.COMMITTED
    assert state_of(log, Level.ATTEMPT, "t1-a1") is AttemptState.REJECTED
    assert state_of(log, Level.ATTEMPT, "t1-t2a1") is AttemptState.COMMITTED
    assert len(implementer.seen) == 1  # the implementer is not asked again
    extra = author.seen[1]
    assert extra.task.role is Producer.TEST_AUTHOR
    assert extra.task.reviews == "t1-s"
    assert extra.task.stage_id == "t1-t2"
    assert extra.task.test_root == "tests"
    assert extra.previous_rejection is not None
    assert "src/a.py:2" in extra.previous_rejection
    assert "no test runs this new line" in extra.previous_rejection


def test_the_code_is_committed_before_the_new_tests_and_both_reach_the_run(
    world: MemoryWorld,
) -> None:
    author = ScriptedAgent(edits=[TESTS, MORE_TESTS])

    run(world, ScriptedMeasurer(verdicts=(PASSED, UNTESTED, PASSED)), author)

    memory = world.memory
    tip = memory.tip(world.workspace.run_branch)
    reachable = [memory.commits[sha] for sha in memory.ancestors(tip.sha)]
    first_tests = next(c for c in reachable if c.trailer("Stage-Id") == ["t1-t"])
    code = next(c for c in reachable if c.trailer("Stage-Id") == ["t1-s"])
    more_tests = next(c for c in reachable if c.trailer("Stage-Id") == ["t1-t2"])
    assert memory.is_ancestor(first_tests.sha, code.sha)
    assert memory.is_ancestor(code.sha, more_tests.sha)
    assert more_tests.subject.startswith("test: ")
    assert {"tests/test_a.py", "tests/test_b.py", "src/a.py"} <= set(tip.tree)


def test_the_extra_stage_does_not_declare_tests_for_the_criteria(world: MemoryWorld) -> None:
    measurer = ScriptedMeasurer(verdicts=(PASSED, UNTESTED, PASSED))

    run(world, measurer, ScriptedAgent(edits=[TESTS, MORE_TESTS]))

    assert [e is None for e in measurer.expected] == [False, True, True]


def test_the_extra_stage_has_the_attempt_budget_and_an_exhausted_one_blocks_the_task(
    world: MemoryWorld,
) -> None:
    author = ScriptedAgent(edits=[TESTS, MORE_TESTS])
    measurer = ScriptedMeasurer(verdicts=(PASSED, UNTESTED, REJECTED))

    state, log, _ = run(world, measurer, author, Budget(attempts_per_task=2))

    assert state is ExecutionState.DELIVERED
    assert state_of(log, Level.TASK, "t1") is TaskState.BLOCKED
    assert log.state.children_of(Level.ATTEMPT, "t1-t2") == ["t1-t2a1", "t1-t2a2"]
    assert state_of(log, Level.STAGE, "t1-t2") is StageState.EXHAUSTED
    assert state_of(log, Level.STAGE, "t1-s") is StageState.EXHAUSTED
    payload = log.state.transition_payload(Level.TASK, "t1", TaskState.BLOCKED)
    assert payload is not None
    assert payload["reason"] == "tests_for_new_lines_exhausted"
    assert payload["lines"] == ["src/a.py:2"]
    assert "too complex" in str(payload["detail"])


def test_the_second_try_of_the_extra_stage_is_told_why_the_first_was_rejected(
    world: MemoryWorld,
) -> None:
    author = ScriptedAgent(edits=[TESTS, MORE_TESTS])
    measurer = ScriptedMeasurer(verdicts=(PASSED, UNTESTED, REJECTED, PASSED))

    state, log, _ = run(world, measurer, author)

    assert state is ExecutionState.DELIVERED
    assert state_of(log, Level.TASK, "t1") is TaskState.INTEGRATED
    assert author.seen[2].task.stage_id == "t1-t2"
    assert author.seen[2].previous_rejection is not None
    assert "too complex" in author.seen[2].previous_rejection


def test_a_rejection_for_another_reason_stays_with_the_implementer(world: MemoryWorld) -> None:
    author = ScriptedAgent(edits=[TESTS])
    measurer = ScriptedMeasurer(verdicts=(PASSED, REJECTED, PASSED))

    _, log, implementer = run(world, measurer, author)

    assert log.state.children_of(Level.STAGE, "t1") == ["t1-t", "t1-s"]
    assert len(implementer.seen) == 2
    assert state_of(log, Level.TASK, "t1") is TaskState.INTEGRATED


def test_an_untested_line_found_with_others_is_not_sent_to_the_test_author() -> None:
    from forja.core.gates import CheckRun, Finding, FindingKind, Rejected
    from forja.core.gates.effects import decide_effect
    from forja.orchestrator.task_cycle import untested_targets
    from tests.orchestrator.fakes import BLOCKING

    kinds = (FindingKind.UNTESTED_LINE, None)
    result = Rejected(
        findings=tuple(
            Finding(message="m", target=f"a.py:{n}", kind=k) for n, k in enumerate(kinds)
        )
    )
    run_ = CheckRun("mutation", 7, BLOCKING, result, decide_effect(BLOCKING, result))

    assert untested_targets(run_) == []


def test_a_text_that_looks_like_the_finding_is_not_the_finding() -> None:
    from forja.core.gates import CheckRun, Finding, Rejected
    from forja.core.gates.effects import decide_effect
    from forja.orchestrator.task_cycle import untested_targets
    from tests.orchestrator.fakes import BLOCKING

    result = Rejected(findings=(Finding(message="no test runs this new line", target="a.py:1"),))
    run_ = CheckRun("mutation", 7, BLOCKING, result, decide_effect(BLOCKING, result))

    assert untested_targets(run_) == []


def test_a_refactoring_without_a_test_stage_also_returns_to_a_test_author(
    tmp_path: Path,
) -> None:
    world = MemoryWorld(tmp_path)
    author = ScriptedAgent(edits=[MORE_TESTS])
    implementer = ScriptedAgent(edits=[CODE])
    measurer = ScriptedMeasurer(verdicts=(UNTESTED, PASSED))

    outcome, log = world.run(
        measurer=measurer,
        agent=implementer,
        agents={Producer.TEST_AUTHOR: author},
        planner=ScriptedPlanner(),
    )

    assert outcome.state is ExecutionState.DELIVERED
    assert log.state.children_of(Level.STAGE, "t1") == ["t1-s", "t1-t2"]
    assert author.seen[0].task.test_root == "tests"
    assert state_of(log, Level.TASK, "t1") is TaskState.INTEGRATED
