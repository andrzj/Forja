"""The specifier is the first stage of a fix without criteria: it writes none, the Forja stores
what it declared, and the stages after it work from that."""

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import pytest

from forja.core.artifacts.llm_output import Criterion, CriterionLevel, LeftOut
from forja.core.artifacts.models import ArtifactType, Assumption, Producer
from forja.core.artifacts.schemas import CriteriaBody
from forja.core.artifacts.store import ArtifactStore
from forja.core.events import EventLog
from forja.core.states import AttemptState, ExecutionState, Level, StageState, TaskState
from forja.orchestrator.config import Budget, FixRequest, Objective
from forja.orchestrator.outcome import Outcome
from forja.orchestrator.planner import FixPlanner
from forja.orchestrator.ports import Baseline, Expectations, PlannedTask
from tests.orchestrator.fakes import (
    PASSED,
    REJECTED,
    ScriptedAgent,
    ScriptedMeasurer,
    ScriptedPlanner,
)
from tests.orchestrator.harness import MemoryWorld

DESCRIPTION = "- page 1 shows the wrong items\n- the last page is empty"
FIX = FixRequest(description=DESCRIPTION)
CRITERIA = (
    Criterion(id=1, text="page 1 has the first items", level=CriterionLevel.UNIT, origin=("E1",)),
    Criterion(id=2, text="the last page has items", level=CriterionLevel.UNIT, origin=("E2",)),
)
TESTS = {"tests/test_a.py": "def test_a():\n    assert False\n"}
CODE = {"src/a.py": "def f():\n    return 1\n"}
README = {"README.md": "# a\n"}
NOTHING: list[dict[str, str]] = [{}]


@pytest.fixture
def world(tmp_path: Path) -> MemoryWorld:
    found = MemoryWorld(tmp_path)
    found.config = found.config.model_copy(update={"objective": Objective.FIX, "fix": FIX})
    return found


@dataclass
class Run:
    outcome: Outcome
    log: EventLog
    agents: dict[str, ScriptedAgent]


class FixPlannerOf(ScriptedPlanner):
    """The real planner of the fix, so the stages are the ones a run has."""

    def __init__(self, planner: FixPlanner) -> None:
        super().__init__()
        self._planner = planner

    async def plan(
        self, worktree: Path, baseline: Baseline, budget: Budget
    ) -> Sequence[PlannedTask]:
        return await self._planner.plan(worktree, baseline, budget)


def run(world: MemoryWorld, measurer: ScriptedMeasurer, specifier: ScriptedAgent) -> Run:
    agents = {
        "specifier": specifier,
        "author": ScriptedAgent(edits=[TESTS]),
        "implementer": ScriptedAgent(edits=[CODE]),
        "documenter": ScriptedAgent(edits=[README]),
    }
    outcome, log = world.run(
        measurer=measurer,
        agent=agents["implementer"],
        agents={
            Producer.SPECIFIER: specifier,
            Producer.TEST_AUTHOR: agents["author"],
            Producer.DOCUMENTER: agents["documenter"],
        },
        planner=FixPlannerOf(FixPlanner(FIX, ("src/a.py",), "tests")),
    )
    return Run(outcome, log, agents)


def test_a_fix_without_criteria_plans_the_specifier_first_and_one_with_criteria_does_not() -> None:
    given = FixRequest.model_validate(
        {
            "description": "d",
            "criteria": {"criteria": [{"id": 1, "text": "t", "level": "unit", "origin": "x"}]},
        }
    )
    without = asyncio.run(FixPlanner(FIX, ("src",)).plan(Path("."), Baseline(True), Budget()))
    with_them = asyncio.run(FixPlanner(given, ("src",)).plan(Path("."), Baseline(True), Budget()))

    assert without[0].stages == (
        Producer.SPECIFIER,
        Producer.TEST_AUTHOR,
        Producer.IMPLEMENTER,
        Producer.DOCUMENTER,
    )
    assert without[0].intent == DESCRIPTION
    assert with_them[0].stages == (
        Producer.TEST_AUTHOR,
        Producer.IMPLEMENTER,
        Producer.DOCUMENTER,
    )
    assert "Criteria:\n1. t" in with_them[0].intent


def test_the_stages_run_in_order_and_the_specifier_has_its_own_ids(world: MemoryWorld) -> None:
    done = run(world, ScriptedMeasurer(), ScriptedAgent(edits=NOTHING, criteria=CRITERIA))

    state = done.log.state
    assert done.outcome.state is ExecutionState.DELIVERED
    assert state.children_of(Level.STAGE, "t1") == ["t1-c", "t1-t", "t1-s", "t1-d"]
    assert state.children_of(Level.ATTEMPT, "t1-c") == ["t1-ca1"]
    assert state.state_of(Level.STAGE, "t1-c") is StageState.COMMITTED
    assert state.state_of(Level.ATTEMPT, "t1-ca1") is AttemptState.COMMITTED
    assert state.state_of(Level.TASK, "t1") is TaskState.INTEGRATED


def test_the_criteria_are_stored_by_the_forja_as_an_artifact_of_the_run(
    world: MemoryWorld,
) -> None:
    run(world, ScriptedMeasurer(), ScriptedAgent(edits=NOTHING, criteria=CRITERIA))

    stored = ArtifactStore(world.run_dir / "store").get("criteria-t1")

    assert stored.header.type is ArtifactType.CRITERIA
    assert stored.header.producer is Producer.SPECIFIER
    assert stored.header.attempt_id == "t1-ca1"
    assert stored.header.executor is not None
    assert stored.header.executor.cli == "fake-cli"
    assert isinstance(stored.body, CriteriaBody)
    assert stored.body.criteria == CRITERIA


def test_what_the_specifier_left_out_and_guessed_is_kept_as_assumptions(
    world: MemoryWorld,
) -> None:
    guess = Assumption(statement="pages are 10 items", reason="r", missing_evidence="page size")
    left = LeftOut(element="E2", reason="needs a service", missing_evidence="which one")
    agent = ScriptedAgent(
        edits=NOTHING, criteria=CRITERIA[:1], left_out=(left,), assumptions=(guess,)
    )

    run(world, ScriptedMeasurer(), agent)

    header = ArtifactStore(world.run_dir / "store").get("criteria-t1").header
    assert header.assumptions == (guess, left.as_assumption())


def test_the_specifier_commits_nothing_and_each_other_stage_commits_once(
    world: MemoryWorld,
) -> None:
    run(world, ScriptedMeasurer(), ScriptedAgent(edits=NOTHING, criteria=CRITERIA))

    memory = world.memory
    tip = memory.branches[world.workspace.run_branch]
    kinds = [memory.commits[sha].subject.split(":")[0] for sha in memory.ancestors(tip)]
    assert [kinds.count(kind) for kind in ("test", "fix", "docs")] == [1, 1, 1]
    assert "spec" not in kinds


def test_the_measurer_is_told_what_the_input_was_cut_into_and_what_was_declared(
    world: MemoryWorld,
) -> None:
    measurer = ScriptedMeasurer()
    left = LeftOut(element="E2", reason="r", missing_evidence="m")

    run(world, measurer, ScriptedAgent(edits=NOTHING, criteria=CRITERIA[:1], left_out=(left,)))

    expected = measurer.expected[0]
    assert isinstance(expected, Expectations)
    assert [(e.id, e.text) for e in expected.elements] == [
        ("E1", "page 1 shows the wrong items"),
        ("E2", "the last page is empty"),
    ]
    assert expected.specified == CRITERIA[:1]
    assert expected.left_out == (left,)


def test_the_stages_after_the_specifier_are_told_the_criteria_it_wrote(world: MemoryWorld) -> None:
    measurer = ScriptedMeasurer()

    agents = run(world, measurer, ScriptedAgent(edits=NOTHING, criteria=CRITERIA)).agents

    told = "\n\nCriteria:\n1. page 1 has the first items\n2. the last page has items"
    for name in ("author", "implementer", "documenter"):
        assert agents[name].seen[0].task.intent == DESCRIPTION + told
    assert agents["specifier"].seen[0].task.intent == DESCRIPTION
    for_the_author = measurer.expected[1]
    assert isinstance(for_the_author, Expectations)
    assert for_the_author.criteria == frozenset({1, 2})


def test_a_specifier_rejected_by_a_gate_is_tried_again_and_only_the_good_one_is_stored(
    world: MemoryWorld,
) -> None:
    measurer = ScriptedMeasurer(verdicts=(REJECTED, PASSED))

    done = run(world, measurer, ScriptedAgent(edits=NOTHING, criteria=CRITERIA))

    state = done.log.state
    assert done.outcome.state is ExecutionState.DELIVERED
    assert state.children_of(Level.ATTEMPT, "t1-c") == ["t1-ca1", "t1-ca2"]
    assert state.state_of(Level.ATTEMPT, "t1-ca1") is AttemptState.REJECTED
    assert ArtifactStore(world.run_dir / "store").header("criteria-t1").attempt_id == "t1-ca2"


def test_a_specifier_that_never_passes_blocks_the_task_before_any_other_stage(
    world: MemoryWorld,
) -> None:
    done = run(
        world,
        ScriptedMeasurer(verdicts=(REJECTED,)),
        ScriptedAgent(edits=NOTHING, criteria=CRITERIA),
    )

    state = done.log.state
    assert state.state_of(Level.TASK, "t1") is TaskState.BLOCKED
    assert state.state_of(Level.STAGE, "t1-c") is StageState.EXHAUSTED
    assert not state.has_target(Level.STAGE, "t1-t")
