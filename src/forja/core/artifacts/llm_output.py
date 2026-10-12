"""The output contract of every role: claims with evidence, actions, and assumptions. Nothing else.

A claim without a citation, an action without files, or an assumption without its missing
evidence is rejected, and the problems are readable enough to be sent back to the model.
"""

import json
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from forja.core.artifacts.errors import InvalidLlmOutput
from forja.core.artifacts.models import Assumption, NonEmpty
from forja.core.manifest import ManifestDiff

_DRIVE = re.compile(r"^[A-Za-z]:")


def _strict() -> ConfigDict:
    return ConfigDict(frozen=True, extra="forbid")


class FileCitation(BaseModel):
    """``path:line`` evidence; the verifier later checks that the lines exist and say so."""

    model_config = _strict()

    kind: Literal["file"]
    path: str
    line_start: int = Field(ge=1)
    line_end: int = Field(ge=1)

    @field_validator("path")
    @classmethod
    def _path(cls, value: str) -> str:
        return check_relative_path(value)

    @model_validator(mode="after")
    def _range(self) -> Self:
        if self.line_end < self.line_start:
            raise ValueError("line_end is before line_start")
        return self


class EvidenceCitation(BaseModel):
    """A recorded measurement."""

    model_config = _strict()

    kind: Literal["evidence"]
    evidence_id: NonEmpty


class FactCitation(BaseModel):
    """A recorded fact (a premise a person confirmed)."""

    model_config = _strict()

    kind: Literal["fact"]
    fact_id: NonEmpty


Citation = Annotated[FileCitation | EvidenceCitation | FactCitation, Field(discriminator="kind")]


class Claim(BaseModel):
    """A statement about the code or the run. Without a citation it is not accepted."""

    model_config = _strict()

    statement: NonEmpty
    citations: tuple[Citation, ...] = Field(min_length=1)


class DeclaredChange(StrEnum):
    CREATED = "created"
    MODIFIED = "modified"
    REMOVED = "removed"


class DeclaredFile(BaseModel):
    model_config = _strict()

    path: str
    change: DeclaredChange

    @field_validator("path")
    @classmethod
    def _path(cls, value: str) -> str:
        return check_relative_path(value)


class Action(BaseModel):
    """What was changed and why. Checked against the real diff; it is never executed."""

    model_config = _strict()

    summary: NonEmpty
    reason: NonEmpty
    files: tuple[DeclaredFile, ...] = Field(min_length=1)


class DeclaredTest(BaseModel):
    """A test the test author says covers a criterion; ``test_id`` is the runner's own id."""

    model_config = _strict()

    criterion_id: int = Field(ge=1)
    test_id: NonEmpty
    path: str

    @field_validator("path")
    @classmethod
    def _path(cls, value: str) -> str:
        return check_relative_path(value)


class LlmOutput(BaseModel):
    """The only shape a role may answer with."""

    model_config = _strict()

    claims: tuple[Claim, ...] = ()
    actions: tuple[Action, ...] = ()
    assumptions: tuple[Assumption, ...] = ()
    tests: tuple[DeclaredTest, ...] = ()  # only the test author declares these


class ChangeDeclaration(BaseModel):
    """Body of the ``change_declaration`` artifact. Assumptions live in the artifact header."""

    model_config = _strict()

    claims: tuple[Claim, ...] = ()
    actions: tuple[Action, ...] = ()

    @classmethod
    def from_output(cls, output: LlmOutput) -> Self:
        return cls(claims=output.claims, actions=output.actions)

    def declared_files(self) -> dict[str, set[DeclaredChange]]:
        declared: dict[str, set[DeclaredChange]] = {}
        for action in self.actions:
            for file in action.files:
                declared.setdefault(file.path, set()).add(file.change)
        return declared


def check_relative_path(value: str) -> str:
    """A repository-relative POSIX path with no way out of the repository."""
    parts = value.split("/")
    if (
        value.startswith(("/", "\\"))
        or "\\" in value
        or _DRIVE.match(value)
        or any(part in ("", ".", "..") for part in parts)
    ):
        raise ValueError(f"not a relative POSIX path inside the repository: {value!r}")
    return value


def parse_llm_output(raw: str | bytes) -> LlmOutput:
    """Parse the model's answer strictly; raise ``InvalidLlmOutput`` listing every problem."""
    try:
        data = json.loads(raw)
    except ValueError as error:
        raise InvalidLlmOutput([f"the answer is not valid JSON: {error}"]) from None
    try:
        return LlmOutput.model_validate(data)
    except ValidationError as error:
        problems = [
            f"{'.'.join(str(part) for part in item['loc']) or 'answer'}: {item['msg']}"
            for item in error.errors()
        ]
        raise InvalidLlmOutput(problems) from None


@dataclass(frozen=True)
class Mismatch:
    """A disagreement between what was declared and what the diff shows."""

    path: str
    declared: DeclaredChange | None
    actual: DeclaredChange | None


def compare_with_diff(declaration: ChangeDeclaration, diff: ManifestDiff) -> list[Mismatch]:
    """Files declared must equal files changed, with the same kind of change. Empty means match."""
    actual: dict[str, DeclaredChange] = {}
    for paths, change in (
        (diff.created, DeclaredChange.CREATED),
        (diff.modified, DeclaredChange.MODIFIED),
        (diff.removed, DeclaredChange.REMOVED),
    ):
        for path in paths:
            actual[path] = change

    declared = declaration.declared_files()
    mismatches = []
    for path in sorted(set(declared) | set(actual)):
        declared_kinds = declared.get(path, set())
        real = actual.get(path)
        if real is not None and declared_kinds == {real}:
            continue
        shown = None if not declared_kinds else sorted(declared_kinds)[0]
        mismatches.append(Mismatch(path, shown, real))
    return mismatches
