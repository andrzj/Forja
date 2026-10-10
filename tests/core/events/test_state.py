"""Rules every event must satisfy, and the state rebuilt from events."""

from collections.abc import Iterator
from pathlib import Path

import pytest

from forja.core.events import EventLog, InvalidEvent, RunState
from forja.core.states import (
    AttemptState,
    ExecutionState,
    InvalidTransition,
    Level,
    StageState,
    TaskState,
)
from tests.core.events.support import (
    RUN,
    build_event,
    create_run,
    create_task,
    open_log,
    to_execution_state,
)

E = ExecutionState


@pytest.fixture
def log(tmp_path: Path) -> Iterator[EventLog]:
    with open_log(tmp_path / "events.jsonl") as opened:
        yield opened


def test_a_run_starts_in_preparing_and_walks_the_happy_path(log: EventLog) -> None:
    create_run(log)
    to_execution_state(
        log, E.CONFIRMED, E.MEASURING_BASELINE, E.PLANNING, E.EXECUTING, E.CLOSING, E.DELIVERED
    )

    assert log.state.state_of(Level.EXECUTION, RUN) is E.DELIVERED


def test_creation_must_use_the_initial_state_of_the_level(log: EventLog) -> None:
    with pytest.raises(InvalidEvent, match="must start in preparing"):
        log.append_transition(Level.EXECUTION, RUN, None, E.EXECUTING)


def test_a_target_cannot_be_created_twice(log: EventLog) -> None:
    create_run(log)
    with pytest.raises(InvalidEvent, match="already exists"):
        create_run(log)


def test_the_execution_is_the_run_itself(log: EventLog) -> None:
    with pytest.raises(InvalidEvent, match="the run itself"):
        log.append_transition(Level.EXECUTION, "other", None, E.PREPARING)


def test_children_need_an_existing_parent_of_the_right_level(log: EventLog) -> None:
    create_run(log)
    with pytest.raises(InvalidEvent, match="needs a parent_id"):
        log.append_transition(Level.TASK, "t1", None, TaskState.PENDING)
    with pytest.raises(InvalidEvent, match="does not exist"):
        log.append_transition(Level.TASK, "t1", None, TaskState.PENDING, parent_id="nope")
    create_task(log)
    with pytest.raises(InvalidEvent, match="parent stage 'zz'"):
        log.append_transition(Level.ATTEMPT, "a1", None, AttemptState.CREATED, parent_id="zz")
    with pytest.raises(InvalidEvent, match="parent stage 't1'"):
        log.append_transition(Level.ATTEMPT, "a1", None, AttemptState.CREATED, parent_id="t1")

    log.append_transition(Level.STAGE, "s1", None, StageState.PENDING, parent_id="t1")
    log.append_transition(Level.ATTEMPT, "a1", None, AttemptState.CREATED, parent_id="s1")
    assert log.state.parent_of(Level.ATTEMPT, "a1") == "s1"
    assert log.state.children_of(Level.STAGE, "t1") == ["s1"]


def test_transition_of_an_unknown_target_is_rejected(log: EventLog) -> None:
    create_run(log)
    with pytest.raises(InvalidEvent, match="unknown task"):
        log.append_transition(Level.TASK, "ghost", TaskState.PENDING, TaskState.IN_PROGRESS)


def test_origin_must_be_the_current_state(log: EventLog) -> None:
    create_run(log)
    with pytest.raises(InvalidEvent, match="is preparing, not confirmed"):
        log.append_transition(Level.EXECUTION, RUN, E.CONFIRMED, E.MEASURING_BASELINE)


def test_forbidden_transition_is_rejected_and_nothing_is_written(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    with open_log(path) as log:
        create_run(log)
        before = path.read_bytes()

        with pytest.raises(InvalidTransition):
            log.append_transition(Level.EXECUTION, RUN, E.PREPARING, E.DELIVERED)

        assert path.read_bytes() == before
        to_execution_state(log, E.CONFIRMED)  # the log is still usable


def test_unknown_state_name_is_rejected(log: EventLog) -> None:
    create_run(log)
    with pytest.raises(InvalidEvent, match="is not a execution state"):
        log.append_transition(Level.EXECUTION, RUN, E.PREPARING, TaskState.PENDING)


def _running(log: EventLog) -> None:
    create_run(log)
    to_execution_state(log, E.CONFIRMED, E.MEASURING_BASELINE, E.PLANNING, E.EXECUTING)


def test_paused_returns_to_the_state_it_was_paused_from(log: EventLog) -> None:
    _running(log)
    to_execution_state(log, E.PAUSED, E.EXECUTING)

    assert log.state.state_of(Level.EXECUTION, RUN) is E.EXECUTING


def test_paused_cannot_return_anywhere_else(log: EventLog) -> None:
    _running(log)
    to_execution_state(log, E.PAUSED)

    with pytest.raises(InvalidTransition):
        log.append_transition(Level.EXECUTION, RUN, E.PAUSED, E.PLANNING)
    with pytest.raises(InvalidTransition):
        log.append_transition(Level.EXECUTION, RUN, E.PAUSED, E.CLOSING)


def test_failed_returns_to_the_last_state_and_a_failure_during_pause_unwinds_in_order(
    log: EventLog,
) -> None:
    _running(log)
    to_execution_state(log, E.PAUSED, E.FAILED)  # failed while paused
    to_execution_state(log, E.PAUSED)  # back to the last state: paused
    to_execution_state(log, E.EXECUTING)  # and paused goes back to where it began

    assert log.state.state_of(Level.EXECUTION, RUN) is E.EXECUTING


def test_failed_from_a_working_state_returns_to_it(log: EventLog) -> None:
    _running(log)
    to_execution_state(log, E.FAILED)
    with pytest.raises(InvalidTransition):
        log.append_transition(Level.EXECUTION, RUN, E.FAILED, E.PLANNING)

    to_execution_state(log, E.EXECUTING)
    assert log.state.state_of(Level.EXECUTION, RUN) is E.EXECUTING


def test_failed_then_discarded_is_final(log: EventLog) -> None:
    _running(log)
    to_execution_state(log, E.FAILED, E.DISCARDED)

    with pytest.raises(InvalidTransition):
        log.append_transition(Level.EXECUTION, RUN, E.DISCARDED, E.PREPARING)


def test_intent_needs_a_known_target_and_a_fresh_operation_id(log: EventLog) -> None:
    with pytest.raises(InvalidEvent, match="unknown execution"):
        log.append_intent(Level.EXECUTION, RUN, "run_tool", "op1")
    create_run(log)
    log.append_intent(Level.EXECUTION, RUN, "run_tool", "op1")

    with pytest.raises(InvalidEvent, match="already used"):
        log.append_intent(Level.EXECUTION, RUN, "run_tool", "op1")


def test_effect_closes_exactly_the_matching_intent(log: EventLog) -> None:
    create_run(log)
    with pytest.raises(InvalidEvent, match="without an open intent"):
        log.append_effect(Level.EXECUTION, RUN, "run_tool", "op1")
    log.append_intent(Level.EXECUTION, RUN, "run_tool", "op1")
    with pytest.raises(InvalidEvent, match="does not match"):
        log.append_effect(Level.EXECUTION, RUN, "push_run_branch", "op1")
    assert set(log.state.open_operations) == {"op1"}

    log.append_effect(Level.EXECUTION, RUN, "run_tool", "op1")

    assert log.state.open_operations == {}
    with pytest.raises(InvalidEvent, match="without an open intent"):
        log.append_effect(Level.EXECUTION, RUN, "run_tool", "op1")
    with pytest.raises(InvalidEvent, match="already used"):
        log.append_intent(Level.EXECUTION, RUN, "run_tool", "op1")


def test_intent_without_effect_is_an_open_operation_with_its_details(log: EventLog) -> None:
    create_run(log)
    log.append_intent(Level.EXECUTION, RUN, "call_agent_cli", "op7")

    (opened,) = log.state.open_operations.values()
    assert (opened.operation, opened.operation_id, opened.level, opened.target_id) == (
        "call_agent_cli",
        "op7",
        Level.EXECUTION,
        RUN,
    )
    assert opened.intent_seq == 2


def test_process_started_is_remembered_until_the_effect(log: EventLog) -> None:
    create_run(log)
    log.append_intent(Level.EXECUTION, RUN, "run_tool", "op1")
    log.append_progress(
        Level.EXECUTION,
        RUN,
        "process_started",
        operation="run_tool",
        operation_id="op1",
        payload={"pid": 4242, "creation_token": 99},
    )

    (identity,) = log.state.leftover_processes()
    assert (identity.pid, identity.creation_token) == (4242, 99)

    log.append_effect(Level.EXECUTION, RUN, "run_tool", "op1")
    assert log.state.leftover_processes() == []


def test_process_started_without_an_open_operation_is_rejected(log: EventLog) -> None:
    create_run(log)
    with pytest.raises(InvalidEvent, match="open operation"):
        log.append_progress(
            Level.EXECUTION, RUN, "process_started", operation_id="nope", payload={"pid": 1}
        )


def test_other_progress_never_changes_the_state(log: EventLog) -> None:
    create_run(log)
    log.append_progress(Level.EXECUTION, RUN, "output", payload={"line": "hello"})

    assert log.state.state_of(Level.EXECUTION, RUN) is E.PREPARING
    assert log.state.open_operations == {}


def test_envelope_rules_run_id_sequence_and_chain() -> None:
    state = RunState("run1")

    with pytest.raises(InvalidEvent, match="not 'run1'"):
        state.validate(build_event(state, run_id="other"))
    with pytest.raises(InvalidEvent, match="expected seq 1"):
        state.validate(build_event(state, seq=5))
    with pytest.raises(InvalidEvent, match="prev does not match"):
        state.validate(build_event(state, prev="1" * 64))

    event = build_event(state)
    state.apply(event)
    assert (state.last_seq, state.last_hash) == (1, event.hash)
    with pytest.raises(InvalidEvent, match="expected seq 2"):
        state.validate(event)


def test_an_open_operation_remembers_what_its_intent_said(log: EventLog) -> None:
    create_run(log)

    log.append_intent(Level.EXECUTION, RUN, "push_run_branch", "op1", payload={"branch": "b"})

    (open_operation,) = log.state.open_operations.values()
    assert open_operation.payload == {"branch": "b"}
    assert log.state.effect_of("op1") is None


def test_the_effect_that_closed_an_operation_can_be_read_back(log: EventLog) -> None:
    create_run(log)
    log.append_intent(Level.EXECUTION, RUN, "push_run_branch", "op1")

    log.append_effect(
        Level.EXECUTION, RUN, "push_run_branch", "op1", payload={"reconciled": "redo"}
    )

    assert log.state.effect_of("op1") == {"reconciled": "redo"}
    assert log.state.open_operations == {}
    assert log.state.effect_of("never-used") is None
