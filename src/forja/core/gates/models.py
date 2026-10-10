"""The four results a gate can return, and the vocabulary around them (contract 5)."""

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from forja.core.artifacts.models import NonEmpty
from forja.core.artifacts.schemas import RepoPath


class Mode(StrEnum):
    BLOCKING = "blocking"  # the result decides the attempt
    OBSERVATION = "observation"  # measure and report, never block


class InconclusivePolicy(StrEnum):
    BLOCK = "block"  # a measurement that could not be made blocks the task
    PREMISE = "premise"  # keep going and declare the gap as an assumption


class Effect(StrEnum):
    """What the orchestrator must do after a check, given its result, mode and policy."""

    PASS = "pass"
    REJECT_ATTEMPT = "reject_attempt"  # the reason goes to the next attempt
    BLOCK_TASK = "block_task"  # not the agent's fault: the attempt does not count as a failure
    CONTINUE_WITH_ASSUMPTION = "continue_with_assumption"
    REPORT_ONLY = "report_only"  # observation mode: shown in the PR, nothing else


class InconclusiveReason(StrEnum):
    TOOL_FAILED = "tool_failed"
    TIMED_OUT = "timed_out"
    UNSUPPORTED_CONSTRUCT = "unsupported_construct"


def _strict() -> ConfigDict:
    return ConfigDict(frozen=True, extra="forbid")


class Location(BaseModel):
    model_config = _strict()

    path: RepoPath
    line: int | None = Field(default=None, ge=1)

    def __str__(self) -> str:
        return self.path if self.line is None else f"{self.path}:{self.line}"


class Finding(BaseModel):
    """One violation: what, where, and the numbers behind it."""

    model_config = _strict()

    message: NonEmpty
    target: NonEmpty
    location: Location | None = None
    measured: float | None = Field(default=None, allow_inf_nan=False)
    limit: float | None = Field(default=None, allow_inf_nan=False)

    def describe(self) -> str:
        text = f"{self.message} [{self.target}"
        if self.location is not None:
            text += f" at {self.location}"
        text += "]"
        if self.measured is not None and self.limit is not None:
            text += f" measured {self.measured:g}, limit {self.limit:g}"
        elif self.measured is not None:
            text += f" measured {self.measured:g}"
        return text


class Approved(BaseModel):
    model_config = _strict()

    result: Literal["approved"] = "approved"


class Rejected(BaseModel):
    """The criterion was violated. Always says what, where and by how much."""

    model_config = _strict()

    result: Literal["rejected"] = "rejected"
    findings: tuple[Finding, ...] = Field(min_length=1)

    def feedback(self) -> str:
        """The reason handed to the next attempt, one line per finding."""
        return "\n".join(finding.describe() for finding in self.findings)


class Inconclusive(BaseModel):
    """The measurement could not be made. Never counts as a pass or as the agent's failure."""

    model_config = _strict()

    result: Literal["inconclusive"] = "inconclusive"
    reason: InconclusiveReason
    detail: NonEmpty
    tool_run_ids: tuple[NonEmpty, ...] = ()


class NotApplicable(BaseModel):
    """The adapter does not offer what the check needs; nobody expected it to work."""

    model_config = _strict()

    result: Literal["not_applicable"] = "not_applicable"
    missing_capability: NonEmpty


GateResult = Annotated[
    Approved | Rejected | Inconclusive | NotApplicable, Field(discriminator="result")
]
RESULT_ADAPTER: TypeAdapter[GateResult] = TypeAdapter(GateResult)
