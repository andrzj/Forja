"""A fix task interrupted at any line of its log resumes and ends where an uninterrupted one ends.

The two stages, the digest of the frozen tests written when the first commits, and the cut between
the commit of an attempt and the commit of its stage are the boundaries a refactoring does not have.
"""

import copy
from pathlib import Path
from typing import Any

import pytest

from forja.core.artifacts.models import Producer
from forja.core.events import EventLog, LogUnusable
from forja.core.states import AttemptState, ExecutionState, Level, StageState
from forja.orchestrator.config import ExecutorRef, FixRequest, Objective
from forja.orchestrator.ports import PlannedTask
from tests.orchestrator.crash import Counting, CrashAfter, Interrupted
from tests.orchestrator.fakes import ScriptedAgent, ScriptedMeasurer, ScriptedPlanner
from tests.orchestrator.harness import RUN, MemoryWorld

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
STAGES = {"t1-t": "t1-ta", "t1-s": "t1-a"}  # stage -> prefix of its attempts


def world_at(root: Path) -> MemoryWorld:
    found = MemoryWorld(root)
    found.config = found.config.model_copy(
        update={
            "objective": Objective.FIX,
            "fix": FIX,
            "test_author": ExecutorRef(name="author-cli", path="/bin/author", version="2.0"),
        }
    )
    return found


def fix_run(world: MemoryWorld, log: EventLog) -> tuple[Any, EventLog]:
    return world.run(
        log=log,
        measurer=ScriptedMeasurer(),
        agent=ScriptedAgent(edits=[CODE]),
        agents={Producer.TEST_AUTHOR: ScriptedAgent(edits=[TESTS])},
        planner=ScriptedPlanner((TASK,)),
    )


def fingerprint(world: MemoryWorld, log: EventLog) -> dict[str, Any]:
    """The facts two runs must share to have ended in the same place."""
    state = log.state
    branch = world.workspace.run_branch
    attempts: dict[str, dict[str, int]] = {}
    for stage in STAGES:
        counts: dict[str, int] = {}
        for attempt in state.children_of(Level.ATTEMPT, stage):
            found = state.state_of(Level.ATTEMPT, attempt)
            assert isinstance(found, AttemptState)
            counts[found.value] = counts.get(found.value, 0) + 1
        attempts[stage] = counts
    return {
        "execution": state.state_of(Level.EXECUTION, RUN).value,
        "task": state.state_of(Level.TASK, "t1").value,
        "stages": {s: state.state_of(Level.STAGE, s).value for s in STAGES},
        "attempts": attempts,
        "frozen": state.transition_payload(Level.STAGE, "t1-t", StageState.COMMITTED),
        "open_operations": sorted(state.open_operations),
        "tree": dict(world.memory.tip(branch).tree),
        "subjects": [c.subject for c in world.memory.log(branch)],
        "worktrees": len(world.memory.worktrees),
    }


@pytest.fixture(scope="module")
def reference(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    """An uninterrupted run: its facts, and the line each event landed on."""
    world = world_at(tmp_path_factory.mktemp("reference"))
    counter = Counting()
    marks: list[tuple[int, str]] = []
    log = world.open(write=counter)
    log.subscribe(lambda e: marks.append((counter.count, e.type)))
    outcome, log = fix_run(world, log)
    assert outcome.state is ExecutionState.DELIVERED
    return {"fingerprint": fingerprint(world, log), "lines": counter.count, "marks": marks}


# Lines the uninterrupted fix writes, and the cuts made in it: after every event that is not a
# progress line, and a torn line before every intent and effect. A test fails if they drift.
TOTAL_LINES = 68
CUTS = (
    0, 2, 4, 5, 6, 7, 8, 9, 10, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27,
    28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50,
    51, 52, 53, 54, 55, 56, 57, 58, 59, 60, 61, 62, 63, 65, 66, 67,
)  # fmt: skip
TORN_CUTS = (
    3, 4, 5, 6, 7, 8, 15, 16, 20, 21, 22, 23, 26, 27, 29, 30, 32, 33, 36, 37, 41, 42, 43, 44, 47,
    48, 50, 51, 53, 54, 57, 58, 59, 60, 64, 65,
)  # fmt: skip


def test_an_uninterrupted_fix_has_the_shape_the_cuts_were_made_for(
    reference: dict[str, Any],
) -> None:
    fp = reference["fingerprint"]

    assert (fp["execution"], fp["task"]) == ("delivered", "integrated")
    assert fp["stages"] == {"t1-t": "committed", "t1-s": "committed"}
    assert fp["attempts"] == {"t1-t": {"committed": 1}, "t1-s": {"committed": 1}}
    assert fp["frozen"]["frozen_digest"]
    assert fp["open_operations"] == []
    assert reference["lines"] == TOTAL_LINES
    boundaries = {n for n, kind in reference["marks"] if kind != "progress"}
    assert (boundaries | {0}) - {1} == set(CUTS)
    assert {n - 1 for n, kind in reference["marks"] if kind in ("intent", "effect")} == set(
        TORN_CUTS
    )


# Cuts that leave an agent call begun and its result not acted on: the attempt cannot be trusted,
# so it is discarded and the stage makes one more.
AGENT_CALL_CUTS = {"t1-t": {27, 28}, "t1-s": {48, 49}}

CASES = [(cut, False) for cut in CUTS] + [(cut, True) for cut in TORN_CUTS]


@pytest.mark.parametrize(
    ("cut", "torn"), CASES, ids=[f"{cut}-{'torn' if torn else 'clean'}" for cut, torn in CASES]
)
def test_a_fix_interrupted_after_the_nth_line_resumes_to_the_same_end(
    tmp_path: Path, reference: dict[str, Any], cut: int, torn: bool
) -> None:
    world = world_at(tmp_path)
    try:
        fix_run(world, world.open(write=CrashAfter(cut, torn=torn)))
    except (Interrupted, LogUnusable):
        pass  # the runner may report the dead log instead of the failed write itself
    else:
        raise AssertionError("the run ended before the cut")

    outcome, log = fix_run(world, world.open())

    assert outcome.state is ExecutionState.DELIVERED
    expected = copy.deepcopy(reference["fingerprint"])
    for stage, cuts in AGENT_CALL_CUTS.items():
        if cut in cuts:
            expected["attempts"][stage]["discarded"] = 1
    assert fingerprint(world, log) == expected
