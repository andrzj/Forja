"""A new project is a run of its own objective: the scaffold is the base, the specifier writes the
criteria from the idea and the stages after it work like a fix with no criteria of its own."""

import asyncio
from collections.abc import Sequence
from pathlib import Path

import pytest
from pydantic import ValidationError

from forja.core.artifacts.llm_output import Criterion, CriterionLevel
from forja.core.artifacts.models import Producer
from forja.core.states import ExecutionState, Level, StageState, TaskState
from forja.orchestrator.config import Budget, CreateRequest, Objective, RunConfig
from forja.orchestrator.planner import CreationPlanner
from forja.orchestrator.ports import Baseline, PlannedTask
from tests.orchestrator.fakes import ScriptedAgent, ScriptedMeasurer, ScriptedPlanner
from tests.orchestrator.harness import MemoryWorld

IDEA = "- a command that adds two numbers\n- it refuses text"
CREATE = CreateRequest(description=IDEA, language="python", name="adder")
CRITERIA = (
    Criterion(id=1, text="adding 1 and 2 gives 3", level=CriterionLevel.UNIT, origin=("E1",)),
    Criterion(id=2, text="text is refused", level=CriterionLevel.UNIT, origin=("E2",)),
)
STAGES = (
    Producer.SPECIFIER,
    Producer.TEST_AUTHOR,
    Producer.IMPLEMENTER,
    Producer.DOCUMENTER,
)


class CreationPlannerOf(ScriptedPlanner):
    """The real planner of a creation, so the stages are the ones a run has."""

    def __init__(self, planner: CreationPlanner) -> None:
        super().__init__()
        self._planner = planner

    async def plan(
        self, worktree: Path, baseline: Baseline, budget: Budget
    ) -> Sequence[PlannedTask]:
        return await self._planner.plan(worktree, baseline, budget)


@pytest.fixture
def world(tmp_path: Path) -> MemoryWorld:
    found = MemoryWorld(tmp_path)
    found.config = found.config.model_copy(update={"objective": Objective.CREATE, "create": CREATE})
    return found


def test_a_creation_plans_one_task_from_the_idea_starting_with_the_specifier() -> None:
    planned = asyncio.run(
        CreationPlanner(CREATE, ("src",), "tests").plan(Path("."), Baseline(True), Budget())
    )

    assert len(planned) == 1
    assert planned[0].intent == IDEA
    assert planned[0].scope == ("src",)
    assert planned[0].stages == STAGES
    assert planned[0].test_root == "tests"


def test_the_creation_objective_needs_a_project_request_and_only_it() -> None:
    base = {
        "repo": "r",
        "base_commit": "abc",
        "implementer": {"name": "fake-cli", "path": "/bin/fake", "version": "1.0"},
        "forja_version": "0.0.0",
        "policy_version": "0.0.0+abc",
    }
    assert RunConfig.model_validate({**base, "objective": "create", "create": CREATE.model_dump()})
    with pytest.raises(ValidationError, match="create"):
        RunConfig.model_validate({**base, "objective": "create"})
    with pytest.raises(ValidationError, match="create"):
        RunConfig.model_validate({**base, "objective": "refactor", "create": CREATE.model_dump()})


@pytest.mark.parametrize("name", ["", "Tool", "my_tool", "-a", "a--b", "a-", "1a", "x" * 41, "a b"])
def test_a_project_name_is_lower_case_words_joined_by_hyphens(name: str) -> None:
    with pytest.raises(ValidationError):
        CreateRequest(description=IDEA, language="python", name=name)


def test_the_stages_run_in_order_and_the_criteria_come_from_the_specifier(
    world: MemoryWorld,
) -> None:
    specifier = ScriptedAgent(edits=[{}], criteria=CRITERIA)
    outcome, log = world.run(
        measurer=ScriptedMeasurer(),
        agent=ScriptedAgent(edits=[{"src/adder.py": "def add(a, b):\n    return a + b\n"}]),
        agents={
            Producer.SPECIFIER: specifier,
            Producer.TEST_AUTHOR: ScriptedAgent(edits=[{"tests/test_adder.py": "x = 1\n"}]),
            Producer.DOCUMENTER: ScriptedAgent(edits=[{"README.md": "# adder\n"}]),
        },
        planner=CreationPlannerOf(CreationPlanner(CREATE, (), "tests")),
    )

    state = log.state
    assert outcome.state is ExecutionState.DELIVERED
    assert state.children_of(Level.STAGE, "t1") == ["t1-c", "t1-t", "t1-s", "t1-d"]
    assert state.state_of(Level.STAGE, "t1-c") is StageState.COMMITTED
    assert state.state_of(Level.TASK, "t1") is TaskState.INTEGRATED
    assert specifier.seen[0].task.intent == IDEA
