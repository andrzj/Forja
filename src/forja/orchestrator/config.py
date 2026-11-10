"""What an execution is asked to do, recorded in the event that confirms it.

The preparation builds a ``RunConfig``; the orchestrator never sees the questions that led to it.
The isolation levels keep living in the core's ``Confirmation``; this adds the rest.
"""

from enum import StrEnum
from typing import Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    ValidationError,
    field_validator,
    model_validator,
)

from forja.core.adapters import valid_project_name
from forja.core.adapters.executor import CommandTemplate
from forja.core.artifacts.models import NonEmpty
from forja.core.artifacts.schemas import CriteriaBody
from forja.core.confirmation import Confirmation, ConfirmationError, confirmation_payload
from forja.core.events.state import RunState
from forja.core.redaction import ItemKind, PackageItem, Redactor
from forja.core.states import ExecutionState, Level
from forja.orchestrator.facts import Fact


class Objective(StrEnum):
    REFACTOR = "refactor"
    FIX = "fix"
    INVESTIGATE = "investigate"
    CREATE = "create"


class ExecutorRef(BaseModel):
    """The agent CLI chosen for a role, as the preparation found and proved it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: NonEmpty
    path: NonEmpty
    version: NonEmpty
    model: str = ""  # empty: the model the user configured in the CLI
    # whether the CLI itself holds the role to its permissions; None: not recorded (older run)
    enforces_permissions: bool | None = None
    # how to call a CLI the Forja does not know; None: one of the known CLIs, found by name
    template: CommandTemplate | None = None


class FixRequest(BaseModel):
    """What a fix is asked to do: the defect in words and the criteria its tests must cover.

    Without criteria the specifier writes them from the description, in the first stage."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    description: NonEmpty
    criteria: CriteriaBody | None = None


class CreateRequest(BaseModel):
    """A new project: the idea in words, and the language and name it is scaffolded with.

    The scaffold is made before the run starts; the specifier writes the criteria from the idea."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    description: NonEmpty
    language: NonEmpty
    name: NonEmpty

    @field_validator("name")
    @classmethod
    def _name_is_a_project_name(cls, name: str) -> str:
        if not valid_project_name(name):
            raise ValueError("a project name is lower-case words joined by hyphens, up to 40")
        return name


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
    question: str = ""  # what to find out; present exactly when the objective is INVESTIGATE
    create: CreateRequest | None = None  # present exactly when the objective is CREATE
    budget: Budget = Budget()
    parallel_tasks: int = Field(default=1, ge=1)  # tasks of disjoint scope that run at once
    forja_version: NonEmpty
    policy_version: NonEmpty
    agent_runs_tests: bool = True  # the agent may call `forja agente testar` in its copy
    scope: tuple[str, ...] = ()  # only code under these paths is planned; empty is all of it
    semgrep_config: str = ""  # the rules the person named; empty: the ones in the base commit
    facts: tuple[Fact, ...] = ()  # what the person recorded; evidence in the packages

    @model_validator(mode="after")
    def _request_goes_with_the_objective(self) -> Self:
        if (self.objective is Objective.FIX) != (self.fix is not None):
            raise ValueError("a fix request is required for, and only for, the fix objective")
        if (self.objective is Objective.INVESTIGATE) != bool(self.question):
            raise ValueError("a question is required for, and only for, the investigate objective")
        if (self.objective is Objective.CREATE) != (self.create is not None):
            raise ValueError("a project request is required for, and only for, create")
        return self


WITHHELD = "[texto retido pela redação]"


def _masked(redactor: Redactor, name: str, text: str) -> str:
    result = redactor.redact([PackageItem(ItemKind.TEXT, name, text)])
    return result.items[0].content if result.items else WITHHELD


def redacted_config(config: RunConfig, redactor: Redactor) -> RunConfig:
    """The config with the text a person wrote (facts, question, descriptions) masked.

    The event log keeps the config so a resumed run can read it back; a secret typed into a fact
    would otherwise sit in the log in the clear."""
    update: dict[str, object] = {}
    if config.facts:
        update["facts"] = tuple(
            fact.model_copy(update={"text": _masked(redactor, "fact", fact.text)})
            for fact in config.facts
        )
    if config.question:
        update["question"] = _masked(redactor, "question", config.question)
    if config.fix:
        fix_update: dict[str, object] = {
            "description": _masked(redactor, "fix", config.fix.description)
        }
        if config.fix.criteria:
            fix_update["criteria"] = config.fix.criteria.model_copy(
                update={
                    "criteria": tuple(
                        criterion.model_copy(
                            update={"text": _masked(redactor, "criterion", criterion.text)}
                        )
                        for criterion in config.fix.criteria.criteria
                    )
                }
            )
        update["fix"] = config.fix.model_copy(update=fix_update)
    if config.create:
        update["create"] = config.create.model_copy(
            update={"description": _masked(redactor, "create", config.create.description)}
        )
    return config.model_copy(update=update)


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
