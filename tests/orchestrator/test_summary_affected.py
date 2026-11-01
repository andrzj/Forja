"""Which committed stages rest on a premise: from its stage on, or all when the stage is unknown."""

from pathlib import Path

import pytest

from forja.core.events import EventLog
from forja.core.states import ExecutionState, Level, StageState, TaskState
from forja.orchestrator.summary import Premise, _affected
from tests.core.events.support import FakeClock
from tests.orchestrator.harness import RUN


@pytest.fixture
def log(tmp_path: Path) -> EventLog:
    opened = EventLog.open(tmp_path / "events.jsonl", RUN, clock=FakeClock())
    opened.append_transition(Level.EXECUTION, RUN, None, ExecutionState.PREPARING)
    opened.append_transition(Level.TASK, "t1", None, TaskState.PENDING, parent_id=RUN)
    for stage in ("t1-s", "t1-d"):
        opened.append_transition(Level.STAGE, stage, None, StageState.PENDING, parent_id="t1")
        opened.append_transition(Level.STAGE, stage, StageState.PENDING, StageState.IN_PROGRESS)
        opened.append_transition(Level.STAGE, stage, StageState.IN_PROGRESS, StageState.COMMITTED)
    return opened


def test_the_stages_from_the_one_the_premise_arose_in_rest_on_it(log: EventLog) -> None:
    assert _affected(log.state, Premise("t1", "t1-a1", "", stage="t1-d")) == ["t1-d"]
    assert _affected(log.state, Premise("t1", "t1-a1", "", stage="t1-s")) == ["t1-s", "t1-d"]


def test_a_premise_from_a_stage_the_task_does_not_have_blames_all_of_them(log: EventLog) -> None:
    assert _affected(log.state, Premise("t1", "t1-a1", "", stage="nowhere")) == ["t1-s", "t1-d"]
