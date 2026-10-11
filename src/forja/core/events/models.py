"""Event records of contract 4. Events never carry content, only ids, hashes and small facts."""

import hashlib
import json
from collections.abc import Mapping
from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    StringConstraints,
    TypeAdapter,
    field_validator,
)

from forja.core.states import Level

SCHEMA_VERSION = 1
GENESIS_HASH = "0" * 64
MAX_PAYLOAD_BYTES = 4096

Sha256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
_TIMESTAMP = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z$"
Timestamp = Annotated[str, StringConstraints(pattern=_TIMESTAMP)]
NonEmpty = Annotated[str, StringConstraints(min_length=1)]


class RefKind(StrEnum):
    ARTIFACT = "artifact"
    EVIDENCE = "evidence"
    TOOL_RUN = "tool_run"
    GATE_DECISION = "gate_decision"
    SENT_PACKAGE = "sent_package"


class Ref(BaseModel):
    """Pointer to something stored elsewhere; the event keeps the id and hash, not the content."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: RefKind
    id: NonEmpty
    hash: Sha256


class _EventBase(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: int
    seq: int = Field(ge=1)
    time: Timestamp
    run_id: NonEmpty
    level: Level
    target_id: NonEmpty
    refs: tuple[Ref, ...] = ()
    payload: dict[str, JsonValue] = {}
    prev: Sha256
    hash: Sha256

    @field_validator("payload")
    @classmethod
    def _payload_is_small(cls, payload: dict[str, JsonValue]) -> dict[str, JsonValue]:
        size = len(canonical_json(payload))
        if size > MAX_PAYLOAD_BYTES:
            raise ValueError(f"payload is {size} bytes; the limit is {MAX_PAYLOAD_BYTES}")
        return payload


class TransitionEvent(_EventBase):
    """A state change. ``from_state`` is ``None`` only when the target is created."""

    type: Literal["transition"]
    from_state: NonEmpty | None
    to_state: NonEmpty
    parent_id: NonEmpty | None = None


class IntentEvent(_EventBase):
    """Written before an operation with side effects starts."""

    type: Literal["intent"]
    operation: NonEmpty
    operation_id: NonEmpty


class EffectEvent(_EventBase):
    """Written after the operation ended; pairs with its intent by ``operation_id``."""

    type: Literal["effect"]
    operation: NonEmpty
    operation_id: NonEmpty


class ProgressEvent(_EventBase):
    """Display-only facts. Resuming ignores them for state; ``payload['kind']`` says what it is."""

    type: Literal["progress"]
    operation: NonEmpty | None = None
    operation_id: NonEmpty | None = None

    @field_validator("payload")
    @classmethod
    def _has_kind(cls, payload: dict[str, JsonValue]) -> dict[str, JsonValue]:
        if not isinstance(payload.get("kind"), str):
            raise ValueError("progress payload needs a string 'kind'")
        return payload


Event = Annotated[
    TransitionEvent | IntentEvent | EffectEvent | ProgressEvent, Field(discriminator="type")
]
EVENT_ADAPTER: TypeAdapter[Event] = TypeAdapter(Event)


def format_time(moment: datetime) -> str:
    """UTC with microseconds, the one timestamp format of every record."""
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def canonical_json(data: Mapping[str, Any] | Any) -> bytes:
    """Deterministic JSON: sorted keys, no spaces, ASCII only."""
    # ensure_ascii is json's default and "ASCII" names the same codec; both are spelled out for
    # the reader, so a change to either leaves the output as it was.
    text = json.dumps(
        data, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )  # pragma: no mutate
    return text.encode("ascii")  # pragma: no mutate


def compute_hash(body: Mapping[str, Any]) -> str:
    """Hash of an event without its own ``hash`` field; ``prev`` inside it chains the log."""
    return hashlib.sha256(canonical_json(body)).hexdigest()
