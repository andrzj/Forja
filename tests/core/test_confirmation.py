from pathlib import Path

import pytest
from pydantic import JsonValue

from forja.core.confirmation import (
    Confirmation,
    ConfirmationError,
    confirmation_payload,
    load_confirmation,
)
from forja.core.events import EventLog
from forja.core.isolation import IsolationLevel, IsolationRecord
from forja.core.states import ExecutionState, Level
from tests.core.events.support import RUN, create_run, open_log

CONFIRMATION = Confirmation(
    IsolationRecord(
        agent=IsolationLevel.ENVIRONMENT,
        repo_code=IsolationLevel.ENVIRONMENT,
        notes=("only builds on Windows",),
    ),
)


def confirm(log: EventLog, payload: dict[str, JsonValue]) -> None:
    log.append_transition(
        Level.EXECUTION, RUN, ExecutionState.PREPARING, ExecutionState.CONFIRMED, payload=payload
    )


def test_what_the_user_confirmed_is_found_again_when_the_run_is_resumed(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    with open_log(path) as log:
        create_run(log)
        confirm(log, confirmation_payload(CONFIRMATION))

    with open_log(path) as resumed:
        assert load_confirmation(resumed.state) == CONFIRMATION


def test_a_run_that_was_not_confirmed_has_no_isolation(tmp_path: Path) -> None:
    with open_log(tmp_path / "events.jsonl") as log:
        with pytest.raises(ConfirmationError, match="never confirmed"):
            load_confirmation(log.state)
        create_run(log)
        with pytest.raises(ConfirmationError, match="never confirmed"):
            load_confirmation(log.state)


def test_a_damaged_confirmation_is_refused_not_guessed(tmp_path: Path) -> None:
    with open_log(tmp_path / "events.jsonl") as log:
        create_run(log)
        confirm(log, {"isolation": {}})

        with pytest.raises(ConfirmationError, match="invalid"):
            load_confirmation(log.state)


def test_the_payload_is_small_enough_for_an_event() -> None:
    import json

    assert len(json.dumps(confirmation_payload(CONFIRMATION))) < 1024


def test_the_latest_transition_into_a_state_is_the_one_remembered(tmp_path: Path) -> None:
    with open_log(tmp_path / "events.jsonl") as log:
        create_run(log)
        confirm(log, {"note": "first"})
        log.append_transition(
            Level.EXECUTION, RUN, ExecutionState.CONFIRMED, ExecutionState.MEASURING_BASELINE
        )
        log.append_transition(
            Level.EXECUTION,
            RUN,
            ExecutionState.MEASURING_BASELINE,
            ExecutionState.PAUSED,
            payload={"why": "network"},
        )
        state = log.state

        assert state.transition_payload(Level.EXECUTION, RUN, ExecutionState.CONFIRMED) == {
            "note": "first"
        }
        assert state.transition_payload(Level.EXECUTION, RUN, ExecutionState.PAUSED) == {
            "why": "network"
        }
        assert state.transition_payload(Level.EXECUTION, RUN, ExecutionState.EXECUTING) is None
