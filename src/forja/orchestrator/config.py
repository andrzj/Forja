"""What an execution is asked to do, recorded in the event that confirms it.

The preparation builds a ``RunConfig``; the orchestrator never sees the questions that led to it.
Grants and isolation levels keep living in the core's ``Confirmation``; this adds the rest.
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationError

from forja.core.artifacts.models import NonEmpty
from forja.core.confirmation import Confirmation, ConfirmationError, confirmation_payload
from forja.core.events.state import RunState
from forja.core.states import ExecutionState, Level


class Objective(StrEnum):
    REFACTOR = "refactor"


class ExecutorRef(BaseModel):
    """The agent CLI chosen for a role, as the preparation found and proved it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: NonEmpty
    path: NonEmpty
    version: NonEmpty


class Budget(BaseModel):
    """Limits that end an execution or a task. Defaults are the ones agreed for increment 1."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    seconds: int = Field(default=7200, ge=60)
    attempts_per_task: int = Field(default=3, ge=1)
    tasks: int = Field(default=5, ge=1)
    files_per_task: int = Field(default=8, ge=1)
    lines_per_task: int = Field(default=400, ge=1)
    infra_failures: int = Field(default=3, ge=1)


class RunConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    repo: NonEmpty
    objective: Objective
    implementer: ExecutorRef
    budget: Budget = Budget()
    forja_version: NonEmpty
    policy_version: NonEmpty


def confirmed_payload(config: RunConfig, confirmation: Confirmation) -> dict[str, JsonValue]:
    """Payload for the ``preparing -> confirmed`` transition: grants, isolation and the config."""
    payload = confirmation_payload(confirmation)
    payload["config"] = config.model_dump(mode="json")
    return payload


def load_config(state: RunState) -> RunConfig:
    """Read the config back from the events of a run, as a resumed process must."""
    payload = (
        state.transition_payload(Level.EXECUTION, state.run_id, ExecutionState.CONFIRMED)
        if state.has_target(Level.EXECUTION, state.run_id)
        else None
    )
    if payload is None:
        raise ConfirmationError("the run was never confirmed")
    try:
        return RunConfig.model_validate(payload.get("config"))
    except ValidationError as error:
        raise ConfirmationError(
            f"the run configuration is invalid: {error.errors()[0]['msg']}"
        ) from None
