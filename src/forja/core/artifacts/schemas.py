"""Bodies of the artifact types that roles hand to each other (contract 4).

Assumptions are not repeated here: every artifact carries them in its header.
"""

from enum import StrEnum
from typing import Annotated, Self

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator, model_validator

from forja.core.artifacts.llm_output import Claim, DeclaredChange, check_relative_path
from forja.core.artifacts.models import Executor, GitCommit, NonEmpty, Producer


def _strict() -> ConfigDict:
    return ConfigDict(frozen=True, extra="forbid")


def _unique(values: list[str], what: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{what} must be unique")


RepoPath = Annotated[str, AfterValidator(check_relative_path)]


# -- findings (archaeologist) ------------------------------------------------------------------


class FindingsBody(BaseModel):
    """What was found in the code, each statement backed by a citation."""

    model_config = _strict()

    claims: tuple[Claim, ...] = ()


# -- criteria (specifier) ----------------------------------------------------------------------


class CriterionLevel(StrEnum):
    UNIT = "unit"
    INTEGRATION = "integration"
    E2E = "e2e"


class Criterion(BaseModel):
    """A numbered, verifiable acceptance criterion and the part of the input it comes from."""

    model_config = _strict()

    id: int = Field(ge=1)
    text: NonEmpty
    level: CriterionLevel
    origin: NonEmpty


class CriteriaBody(BaseModel):
    model_config = _strict()

    criteria: tuple[Criterion, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _numbers_are_unique(self) -> Self:
        _unique([str(c.id) for c in self.criteria], "criterion ids")
        return self


# -- authored tests (test author) --------------------------------------------------------------


class CriterionTest(BaseModel):
    """Which test covers which criterion."""

    model_config = _strict()

    criterion_id: int = Field(ge=1)
    test_id: NonEmpty
    path: RepoPath


class DataGenerator(BaseModel):
    """A seeded generator of test data, so fixtures are reproducible and never real data."""

    model_config = _strict()

    name: NonEmpty
    seed: int = Field(ge=0)
    path: RepoPath


class AuthoredTestsBody(BaseModel):
    model_config = _strict()

    tests: tuple[CriterionTest, ...] = Field(min_length=1)
    generators: tuple[DataGenerator, ...] = ()

    @model_validator(mode="after")
    def _names_are_unique(self) -> Self:
        _unique([t.test_id for t in self.tests], "test ids")
        _unique([g.name for g in self.generators], "generator names")
        return self


# -- change record (documenter) ----------------------------------------------------------------


class RecordedFile(BaseModel):
    model_config = _strict()

    path: RepoPath
    change: DeclaredChange


class RecordedSymbol(BaseModel):
    """``kind`` is free text for now (function, class...); adapters fix the values later."""

    model_config = _strict()

    path: RepoPath
    name: NonEmpty
    kind: NonEmpty
    change: DeclaredChange


class ToolVersion(BaseModel):
    model_config = _strict()

    name: NonEmpty
    version: NonEmpty


class ChangeRecordBody(BaseModel):
    """The factual record of a task: what changed, how it was measured, how to revert it."""

    model_config = _strict()

    files: tuple[RecordedFile, ...] = ()
    symbols: tuple[RecordedSymbol, ...] = ()
    evidence_before: tuple[NonEmpty, ...] = ()
    evidence_after: tuple[NonEmpty, ...] = ()
    gates_passed: tuple[NonEmpty, ...] = ()
    toolchains: tuple[ToolVersion, ...] = ()
    executors: tuple[Executor, ...] = ()
    revert_commit: GitCommit


# -- execution summary (closing) ---------------------------------------------------------------


class TaskOutcomeKind(StrEnum):
    INTEGRATED = "integrated"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"


class TaskOutcome(BaseModel):
    """How one task ended. Time and tokens are optional because not every CLI reports them."""

    model_config = _strict()

    task_id: NonEmpty
    outcome: TaskOutcomeKind
    attempts: int = Field(ge=0)
    rejected_attempts: int = Field(ge=0)
    duration_seconds: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    tokens: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _rejections_fit_in_attempts(self) -> Self:
        if self.rejected_attempts > self.attempts:
            raise ValueError("rejected_attempts exceeds attempts")
        return self


class ExecutionSummaryBody(BaseModel):
    model_config = _strict()

    tasks: tuple[TaskOutcome, ...] = ()
    evidence_before: tuple[NonEmpty, ...] = ()
    evidence_after: tuple[NonEmpty, ...] = ()
    total_duration_seconds: float | None = Field(default=None, ge=0, allow_inf_nan=False)

    @model_validator(mode="after")
    def _tasks_are_unique(self) -> Self:
        _unique([t.task_id for t in self.tasks], "task ids")
        return self


# -- task definition (planning) ----------------------------------------------------------------


class TaskDefinitionBody(BaseModel):
    """What a task or stage is for, where it may write, and what it waits for."""

    model_config = _strict()

    role: Producer
    intent: NonEmpty
    scope: tuple[RepoPath, ...] = Field(min_length=1)
    max_files: int = Field(ge=1)
    max_lines: int = Field(ge=1)
    depends_on: tuple[NonEmpty, ...] = ()

    @field_validator("scope")
    @classmethod
    def _scope_is_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        _unique(list(value), "scope paths")
        return value

    @field_validator("depends_on")
    @classmethod
    def _dependencies_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        _unique(list(value), "dependencies")
        return value

    @field_validator("role")
    @classmethod
    def _not_forja(cls, value: Producer) -> Producer:
        if value is Producer.FORJA:
            raise ValueError("a task is assigned to a role, not to Forja itself")
        return value
