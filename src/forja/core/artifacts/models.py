"""Artifact header of contract 4: who made it, from what, on which commit, with what content."""

import re
from enum import StrEnum
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, StringConstraints, field_validator, model_validator

from forja.core.events.models import Sha256

ARTIFACT_SCHEMA_VERSION = 1

NonEmpty = Annotated[str, StringConstraints(min_length=1, strip_whitespace=True)]
GitCommit = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{40}([0-9a-f]{24})?$")]

_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
_WINDOWS_DEVICES = {"con", "prn", "aux", "nul"} | {
    f"{n}{i}" for n in ("com", "lpt") for i in range(1, 10)
}


class ArtifactType(StrEnum):
    FINDINGS = "findings"
    CRITERIA = "criteria"
    TEST_MANIFEST = "test_manifest"
    CHANGE_DECLARATION = "change_declaration"
    CHANGE_RECORD = "change_record"
    EXECUTION_SUMMARY = "execution_summary"
    TASK_DEFINITION = "task_definition"


class Producer(StrEnum):
    ARCHAEOLOGIST = "archaeologist"
    SPECIFIER = "specifier"
    TEST_AUTHOR = "test_author"
    IMPLEMENTER = "implementer"
    DOCUMENTER = "documenter"
    FORJA = "forja"  # deterministic code: planning, closing


class Executor(BaseModel):
    """The agent CLI that produced the artifact, with its version."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    cli: NonEmpty
    version: NonEmpty


class InputRef(BaseModel):
    """An artifact this one was made from, pinned by content hash."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    artifact_id: NonEmpty
    content_hash: Sha256


class Assumption(BaseModel):
    """What was assumed for lack of evidence, why, and which evidence was missing."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    statement: NonEmpty
    reason: NonEmpty
    missing_evidence: NonEmpty


def check_artifact_id(value: str) -> str:
    """Ids become file names: letters, digits, ``-`` and ``_`` only, and no Windows device names."""
    if not _SAFE_ID.fullmatch(value):
        raise ValueError(f"unsafe artifact id {value!r}")
    if value.lower() in _WINDOWS_DEVICES:
        raise ValueError(f"{value!r} is a reserved Windows device name")
    return value


class ArtifactHeader(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    type: ArtifactType
    schema_version: int
    producer: Producer
    executor: Executor | None
    attempt_id: NonEmpty | None
    base_commit: GitCommit | None
    content_hash: Sha256
    inputs: tuple[InputRef, ...] = ()
    assumptions: tuple[Assumption, ...] = ()

    @field_validator("id")
    @classmethod
    def _id_is_a_safe_file_name(cls, value: str) -> str:
        return check_artifact_id(value)

    @model_validator(mode="after")
    def _executor_matches_producer(self) -> Self:
        if self.producer is Producer.FORJA and self.executor is not None:
            raise ValueError("an artifact made by Forja itself has no executor")
        if self.producer is not Producer.FORJA and self.executor is None:
            raise ValueError("an artifact made by a role needs its executor (CLI and version)")
        ids = [ref.artifact_id for ref in self.inputs]
        if len(ids) != len(set(ids)):
            raise ValueError("an input artifact is listed twice")
        return self
