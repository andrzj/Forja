from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from forja.core.artifacts.schemas import CriteriaBody
from forja.core.confirmation import (
    Confirmation,
    ConfirmationError,
    confirmation_payload,
    load_confirmation,
)
from forja.core.isolation import IsolationLevel, IsolationRecord
from forja.core.states import ExecutionState, Level
from forja.orchestrator.config import (
    Budget,
    ExecutorRef,
    FixRequest,
    Objective,
    RunConfig,
    confirmed_payload,
    load_config,
)
from forja.orchestrator.outcome import ExitCode, exit_code_for
from tests.core.events.support import RUN, create_run, open_log

CONFIG = RunConfig(
    repo="C:/work/repo",
    base_commit="a" * 40,
    objective=Objective.REFACTOR,
    implementer=ExecutorRef(name="claude-code", path="/usr/bin/claude", version="2.1.0"),
    forja_version="0.0.0",
    policy_version="0.0.0+0123456789ab",
)
CONFIRMATION = Confirmation(
    IsolationRecord(agent=IsolationLevel.ENVIRONMENT, repo_code=IsolationLevel.ENVIRONMENT),
)


def test_the_defaults_are_the_ones_agreed_for_increment_1() -> None:
    budget = Budget()

    assert (budget.tokens, budget.attempts_per_task, budget.tasks) == (2_000_000, 3, 5)
    assert (budget.files_per_task, budget.lines_per_task, budget.infra_failures) == (8, 400, 3)


@pytest.mark.parametrize(
    "field",
    ["attempts_per_task", "tasks", "files_per_task", "lines_per_task", "infra_failures"],
)
def test_a_budget_cannot_be_zero_or_negative(field: str) -> None:
    with pytest.raises(ValidationError):
        Budget(**{field: 0})
    assert Budget(**{field: 1})


def test_a_budget_of_no_tokens_is_refused() -> None:
    with pytest.raises(ValidationError):
        Budget(tokens=0)
    assert Budget(tokens=1).tokens == 1


def test_there_is_no_time_limit_in_the_budget() -> None:
    with pytest.raises(ValidationError):
        Budget(seconds=60)  # type: ignore[call-arg]


def test_unknown_fields_are_refused() -> None:
    with pytest.raises(ValidationError):
        RunConfig.model_validate({**CONFIG.model_dump(mode="json"), "surprise": 1})


def test_the_config_and_the_confirmation_travel_in_one_event_and_come_back(
    tmp_path: Path,
) -> None:
    with open_log(tmp_path / "events.jsonl") as log:
        create_run(log)
        payload = confirmed_payload(CONFIG, CONFIRMATION)

        log.append_transition(
            Level.EXECUTION,
            RUN,
            ExecutionState.PREPARING,
            ExecutionState.CONFIRMED,
            payload=payload,
        )

        assert load_config(log.state) == CONFIG
        assert load_confirmation(log.state) == CONFIRMATION


def test_the_config_is_stored_as_plain_json_values() -> None:
    config: Any = confirmed_payload(CONFIG, CONFIRMATION)["config"]

    assert type(config["objective"]) is str
    assert type(config["implementer"]["name"]) is str


def test_a_run_that_was_never_confirmed_has_no_config(tmp_path: Path) -> None:
    with open_log(tmp_path / "events.jsonl") as log:
        with pytest.raises(ConfirmationError) as before:
            load_config(log.state)
        create_run(log)
        with pytest.raises(ConfirmationError) as after:
            load_config(log.state)

    assert str(before.value) == str(after.value) == "the run was never confirmed"


def test_a_confirmation_without_a_config_is_reported(tmp_path: Path) -> None:
    with open_log(tmp_path / "events.jsonl") as log:
        create_run(log)
        log.append_transition(
            Level.EXECUTION,
            RUN,
            ExecutionState.PREPARING,
            ExecutionState.CONFIRMED,
            payload=confirmation_payload(CONFIRMATION),
        )

        with pytest.raises(ConfirmationError, match="run configuration is invalid"):
            load_config(log.state)


@pytest.mark.parametrize(
    ("state", "code"),
    [
        (ExecutionState.DELIVERED, ExitCode.DELIVERED),
        (ExecutionState.DISCARDED, ExitCode.DELIVERED),
        (ExecutionState.FAILED, ExitCode.FAILED),
        (ExecutionState.PAUSED, ExitCode.PAUSED),
        (ExecutionState.EXECUTING, ExitCode.INTERRUPTED),
        (ExecutionState.CLOSING, ExitCode.INTERRUPTED),
    ],
)
def test_the_exit_code_follows_the_state_the_run_was_left_in(
    state: ExecutionState, code: ExitCode
) -> None:
    assert exit_code_for(state) is code


def test_the_codes_are_the_ones_the_users_scripts_can_rely_on() -> None:
    assert [int(c) for c in ExitCode] == [0, 1, 2, 3, 4, 130]


FIX = FixRequest(
    description="page 1 returns the wrong items",
    criteria=CriteriaBody.model_validate(
        {"criteria": [{"id": 1, "text": "t", "level": "unit", "origin": "task description"}]}
    ),
)


def test_a_fix_run_carries_what_to_fix_and_reads_back() -> None:
    config = CONFIG.model_copy(update={"objective": Objective.FIX, "fix": FIX})

    assert RunConfig.model_validate(config.model_dump(mode="json")) == config


def test_a_fix_objective_without_a_request_is_refused() -> None:
    with pytest.raises(ValidationError, match="fix request"):
        RunConfig(**{**CONFIG.model_dump(), "objective": Objective.FIX})


def test_a_request_to_fix_on_a_refactoring_is_refused() -> None:
    with pytest.raises(ValidationError, match="fix request"):
        RunConfig(**{**CONFIG.model_dump(), "fix": FIX.model_dump()})


def test_a_fix_without_a_description_is_refused() -> None:
    with pytest.raises(ValidationError):
        FixRequest(description="", criteria=FIX.criteria)


def test_the_test_author_is_optional_and_an_old_config_still_reads() -> None:
    assert CONFIG.test_author is None
    old = {
        k: v for k, v in CONFIG.model_dump(mode="json").items() if k not in ("test_author", "fix")
    }

    assert RunConfig.model_validate(old) == CONFIG
    author = ExecutorRef(name="claude-code", path="/usr/bin/claude", version="2.1.0")
    assert CONFIG.model_copy(update={"test_author": author}).test_author == author
