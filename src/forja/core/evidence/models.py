"""Tool run and evidence records of contract 4.

A tool run says what command ran and how it ended. Evidence says what was measured, and always
points to the tool run that produced it. Neither contains a gate decision.
"""

import hashlib
import math
from enum import StrEnum
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from forja.core.artifacts.models import GitCommit, NonEmpty, check_artifact_id
from forja.core.events.models import Sha256, Timestamp
from forja.core.process import Outcome, ProcessResult, ProcessSpec
from forja.core.records import Record

TOOL_RUN_SCHEMA_VERSION = 1
EVIDENCE_SCHEMA_VERSION = 1

_CHUNK = 1 << 20


class ToolRun(Record):
    """One external command: what ran, with which environment names, and how it ended."""

    operation_id: NonEmpty
    command: tuple[str, ...] = Field(min_length=1)
    cwd: NonEmpty
    env_names: tuple[str, ...]
    outcome: Outcome
    exit_code: int | None
    duration_seconds: float = Field(ge=0, allow_inf_nan=False)
    log_path: NonEmpty
    log_sha256: Sha256 | None

    @classmethod
    def from_result(
        cls, record_id: str, operation_id: str, spec: ProcessSpec, result: ProcessResult
    ) -> "ToolRun":
        return cls(
            schema_version=TOOL_RUN_SCHEMA_VERSION,
            id=record_id,
            operation_id=operation_id,
            command=tuple(spec.command),
            cwd=str(spec.cwd),
            env_names=tuple(sorted(spec.env)),
            outcome=result.outcome,
            exit_code=result.exit_code,
            duration_seconds=result.duration,
            log_path=str(result.log_path),
            log_sha256=_file_sha256(Path(result.log_path)),
        )


def _file_sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        # Reading in chunks only bounds memory; the digest is the same either way.
        while chunk := handle.read(_CHUNK):  # pragma: no mutate
            digest.update(chunk)
    return digest.hexdigest()


class TargetKind(StrEnum):
    FILE = "file"
    SYMBOL = "symbol"
    MODULE = "module"


class Target(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: TargetKind
    id: NonEmpty


class MeasurementContext(BaseModel):
    """Everything needed to know whether two measurements are comparable (cache key, contract 5).

    ``config_hash`` and ``policy_version`` are opaque strings given by the adapter. ``scope`` is
    kept sorted and without duplicates, so equal scopes compare equal in any order.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    tool: NonEmpty
    tool_version: NonEmpty
    config_hash: NonEmpty
    toolchain: NonEmpty
    toolchain_version: NonEmpty
    platform: Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_.]+-[A-Za-z0-9_.]+$")]
    scope: tuple[NonEmpty, ...]
    commit: GitCommit
    policy_version: NonEmpty

    @field_validator("scope")
    @classmethod
    def _scope_is_a_sorted_set(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("scope entries must be unique")
        return tuple(sorted(value))


class Evidence(Record):
    """A measurement in the single schema every language adapter normalizes to."""

    measurement: NonEmpty
    target: Target
    value: bool | int | float | str
    unit: NonEmpty
    tool_run_id: str
    measured_at: Timestamp
    context: MeasurementContext

    @field_validator("tool_run_id")
    @classmethod
    def _tool_run_id_is_an_id(cls, value: str) -> str:
        return check_artifact_id(value)

    @field_validator("value")
    @classmethod
    def _value_is_finite(cls, value: bool | int | float | str) -> bool | int | float | str:
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("a measured value must be finite")
        return value
