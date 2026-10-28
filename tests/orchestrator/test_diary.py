"""The log book of a task is read from the log: the same entries after a resume or a cut log."""

from pathlib import Path

import pytest
from pydantic import JsonValue

from forja.core.events import EventLog
from forja.core.events.log import read_state
from forja.core.states import (
    AttemptState,
    ExecutionState,
    Level,
    StageState,
    TaskState,
)
from forja.orchestrator.diary import (
    BLOCKED,
    EXHAUSTED,
    Decision,
    Entry,
    Outcome,
    stage_entries,
    task_decisions,
    task_entries,
)
from tests.core.events.support import FakeClock
from tests.orchestrator.harness import RUN

S = AttemptState


@pytest.fixture
def log(tmp_path: Path) -> EventLog:
    opened = EventLog.open(tmp_path / "events.jsonl", RUN, clock=FakeClock())
    opened.append_transition(Level.EXECUTION, RUN, None, ExecutionState.PREPARING)
    opened.append_transition(Level.TASK, "t1", None, TaskState.PENDING, parent_id=RUN)
    opened.append_transition(Level.STAGE, "t1", None, StageState.PENDING, parent_id="t1")
    return opened


def attempt(
    log: EventLog,
    name: str,
    *,
    said: str | None = None,
    end: AttemptState | None = None,
    payload: dict[str, JsonValue] | None = None,
    stage: str = "t1",
) -> None:
    """Run an attempt through the states up to ``end`` (``None``: left where the agent ran)."""
    log.append_transition(Level.ATTEMPT, name, None, S.CREATED, parent_id=stage)
    log.append_transition(Level.ATTEMPT, name, S.CREATED, S.WORKCOPY_READY)
    log.append_transition(Level.ATTEMPT, name, S.WORKCOPY_READY, S.AGENT_RUNNING)
    if end is None:
        return
    if end is S.DISCARDED:
        log.append_transition(Level.ATTEMPT, name, S.AGENT_RUNNING, S.DISCARDED, payload=payload)
        return
    log.append_transition(
        Level.ATTEMPT, name, S.AGENT_RUNNING, S.VALIDATING, payload={"reason": said or ""}
    )
    log.append_transition(Level.ATTEMPT, name, S.VALIDATING, end, payload=payload)


def test_a_rejected_attempt_keeps_what_the_agent_said_and_why_it_was_rejected(
    log: EventLog,
) -> None:
    attempt(log, "t1-a1", said="renamed it", end=S.REJECTED, payload={"reason": "gate 4 (crap)"})

    assert task_entries(log.state, "t1") == [
        Entry("t1", "t1-a1", "renamed it", Outcome.REJECTED, "gate 4 (crap)")
    ]


def test_an_approved_attempt_lists_the_gates_it_passed(log: EventLog) -> None:
    attempt(log, "t1-a1", said="done", end=S.APPROVED, payload={"gates_passed": ["scope", "lint"]})

    assert stage_entries(log.state, "t1") == [
        Entry("t1", "t1-a1", "done", Outcome.APPROVED, "scope, lint")
    ]


def test_an_approval_without_a_list_of_gates_has_no_detail(log: EventLog) -> None:
    attempt(log, "t1-a1", said="done", end=S.APPROVED, payload={})

    assert stage_entries(log.state, "t1")[0].detail == ""


def test_an_attempt_discarded_for_infrastructure_says_so(log: EventLog) -> None:
    attempt(log, "t1-a1", end=S.DISCARDED, payload={"reason": "network", "infra_failure": True})
    attempt(
        log, "t1-a2", end=S.DISCARDED, payload={"reason": "interrupted", "infra_failure": False}
    )

    first, second = stage_entries(log.state, "t1")

    assert (first.outcome, first.detail, first.infrastructure) == (
        Outcome.DISCARDED,
        "network",
        True,
    )
    assert (second.outcome, second.infrastructure) == (Outcome.DISCARDED, False)
    assert first.said == ""


def test_an_attempt_that_has_not_ended_is_open(log: EventLog) -> None:
    attempt(log, "t1-a1")

    assert stage_entries(log.state, "t1") == [Entry("t1", "t1-a1", "", Outcome.OPEN)]


def test_an_attempt_still_validating_keeps_what_the_agent_said(log: EventLog) -> None:
    log.append_transition(Level.ATTEMPT, "t1-a1", None, S.CREATED, parent_id="t1")
    log.append_transition(Level.ATTEMPT, "t1-a1", S.CREATED, S.WORKCOPY_READY)
    log.append_transition(Level.ATTEMPT, "t1-a1", S.WORKCOPY_READY, S.AGENT_RUNNING)
    log.append_transition(
        Level.ATTEMPT, "t1-a1", S.AGENT_RUNNING, S.VALIDATING, payload={"reason": "half way"}
    )

    assert stage_entries(log.state, "t1") == [Entry("t1", "t1-a1", "half way", Outcome.OPEN)]


def test_the_entries_of_a_task_follow_its_stages_and_attempts_in_order(log: EventLog) -> None:
    log.append_transition(Level.STAGE, "t1-t", None, StageState.PENDING, parent_id="t1")
    attempt(log, "t1-a1", said="a", end=S.REJECTED, payload={"reason": "x"})
    attempt(log, "t1-a2", said="b", end=S.APPROVED, payload={"gates_passed": []})
    attempt(log, "t1-ta1", said="c", end=S.REJECTED, payload={"reason": "y"}, stage="t1-t")

    assert [(e.stage, e.attempt) for e in task_entries(log.state, "t1")] == [
        ("t1", "t1-a1"),
        ("t1", "t1-a2"),
        ("t1-t", "t1-ta1"),
    ]


def test_an_exhausted_stage_and_a_blocked_task_are_decisions_with_their_reason(
    log: EventLog,
) -> None:
    log.append_transition(Level.STAGE, "t1", StageState.PENDING, StageState.IN_PROGRESS)
    log.append_transition(
        Level.STAGE,
        "t1",
        StageState.IN_PROGRESS,
        StageState.EXHAUSTED,
        payload={"reason": "3 attempts"},
    )
    log.append_transition(Level.TASK, "t1", TaskState.PENDING, TaskState.IN_PROGRESS)
    log.append_transition(
        Level.TASK, "t1", TaskState.IN_PROGRESS, TaskState.BLOCKED, payload={"reason": "3 attempts"}
    )

    assert task_decisions(log.state, "t1") == [
        Decision("t1", EXHAUSTED, "3 attempts"),
        Decision("t1", BLOCKED, "3 attempts"),
    ]


def test_a_task_that_went_well_has_no_decision(log: EventLog) -> None:
    assert task_decisions(log.state, "t1") == []


def test_a_decision_without_a_reason_has_an_empty_one(log: EventLog) -> None:
    log.append_transition(Level.TASK, "t1", TaskState.PENDING, TaskState.IN_PROGRESS)
    log.append_transition(Level.TASK, "t1", TaskState.IN_PROGRESS, TaskState.BLOCKED)

    assert task_decisions(log.state, "t1") == [Decision("t1", BLOCKED, "")]


def test_a_log_read_again_gives_the_same_entries(log: EventLog, tmp_path: Path) -> None:
    attempt(log, "t1-a1", said="one", end=S.REJECTED, payload={"reason": "r"})
    attempt(log, "t1-a2", said="two")

    reread = read_state(tmp_path / "events.jsonl", RUN)

    assert task_entries(reread, "t1") == task_entries(log.state, "t1")


def test_a_log_cut_in_the_last_line_gives_the_entries_before_it(
    log: EventLog, tmp_path: Path
) -> None:
    attempt(log, "t1-a1", said="one", end=S.REJECTED, payload={"reason": "r"})
    path = tmp_path / "events.jsonl"
    with path.open("ab") as stream:
        stream.write(b'{"seq": 99, "type": "transi')

    assert task_entries(read_state(path, RUN), "t1") == [
        Entry("t1", "t1-a1", "one", Outcome.REJECTED, "r")
    ]
