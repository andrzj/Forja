"""What an execution is asked to do, recorded in the event that confirms it.

The preparation builds a ``RunConfig``; the orchestrator never sees the questions that led to it.
The isolation levels keep living in the core's ``Confirmation``; this adds the rest.
"""

from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationError, model_validator

from forja.core.artifacts.models import NonEmpty
from forja.core.artifacts.schemas import CriteriaBody
from forja.core.confirmation import Confirmation, ConfirmationError, confirmation_payload
from forja.core.events.state import RunState
from forja.core.states import ExecutionState, Level


class Objective(StrEnum):
    REFACTOR = "refactor"
    FIX = "fix"


class ExecutorRef(BaseModel):
    """The agent CLI chosen for a role, as the preparation found and proved it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: NonEmpty
    path: NonEmpty
    version: NonEmpty
    model: str = ""  # empty: the model the user configured in the CLI
    # whether the CLI itself holds the role to its permissions; None: not recorded (older run)
    enforces_permissions: bool | None = None


class FixRequest(BaseModel):
    """What a fix is asked to do: the defect in words and the criteria its tests must cover."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    description: NonEmpty
    criteria: CriteriaBody


class Budget(BaseModel):
    """Limits that end an execution or a task. Defaults are the ones agreed for increment 1."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    tokens: int = Field(default=2_000_000, ge=1)
    attempts_per_task: int = Field(default=3, ge=1)
    tasks: int = Field(default=5, ge=1)
    files_per_task: int = Field(default=8, ge=1)
    lines_per_task: int = Field(default=400, ge=1)
    infra_failures: int = Field(default=3, ge=1)


class RunConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    repo: NonEmpty
    base_commit: NonEmpty
    objective: Objective
    implementer: ExecutorRef
    test_author: ExecutorRef | None = None  # None: the implementer's executor writes the tests too
    fix: FixRequest | None = None  # what to fix; present exactly when the objective is FIX
    budget: Budget = Budget()
    forja_version: NonEmpty
    policy_version: NonEmpty
    agent_runs_tests: bool = True  # the agent may call `forja agente testar` in its copy
    scope: tuple[str, ...] = ()  # only code under these paths is planned; empty is all of it
    semgrep_config: str = ""  # the rules the person named; empty: the ones in the base commit

    @model_validator(mode="after")
    def _fix_goes_with_the_fix_objective(self) -> Self:
        if (self.objective is Objective.FIX) != (self.fix is not None):
            raise ValueError("a fix request is required for, and only for, the fix objective")
        return self


def confirmed_payload(config: RunConfig, confirmation: Confirmation) -> dict[str, JsonValue]:
    """Payload for the ``preparing -> confirmed`` transition: isolation and the config."""
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
