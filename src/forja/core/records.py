"""Immutable JSON records addressed by id, for tool runs and evidence (contract 4)."""

import hashlib
import json
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

from forja.core.artifacts.models import check_artifact_id
from forja.core.atomic import atomic_write_bytes
from forja.core.events.models import Ref, RefKind, canonical_json


class RecordError(Exception):
    """Base for every problem with stored records."""


class RecordMissing(RecordError):
    def __init__(self, kind: str, record_id: str) -> None:
        self.record_id = record_id
        super().__init__(f"{kind} {record_id!r} is missing")


class RecordCorrupt(RecordError):
    def __init__(self, kind: str, record_id: str, reason: str) -> None:
        self.record_id = record_id
        super().__init__(f"{kind} {record_id!r} is corrupt: {reason}")


class RecordExists(RecordError):
    """The id is taken by a record with different content."""


class UnsupportedRecordVersion(RecordError):
    def __init__(self, kind: str, record_id: str, version: int, supported: int) -> None:
        super().__init__(
            f"{kind} {record_id!r} has schema version {version}, newer than the supported "
            f"{supported}; upgrade Forja to read it"
        )


class Record(BaseModel):
    """Base of every stored record: an id that is safe as a file name and a schema version."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: int
    id: str

    @field_validator("id")
    @classmethod
    def _id_is_a_safe_file_name(cls, value: str) -> str:
        return check_artifact_id(value)


class RecordStore[R: Record]:
    """One folder of ``<id>.json`` files holding canonical JSON.

    A record never changes once written; the reference that events keep is its id plus the
    SHA-256 of the stored bytes, so any later change is detectable with ``verify``.
    """

    def __init__(
        self,
        root: Path,
        *,
        folder: str,
        model: type[R],
        kind: RefKind,
        current_version: int,
        write: Callable[[Path, bytes], None] = atomic_write_bytes,
        upgraders: Mapping[int, Callable[[dict[str, Any]], dict[str, Any]]] | None = None,
    ) -> None:
        self._folder = root / folder
        self._model = model
        self._kind = kind
        self._current_version = current_version
        self._write = write
        self._upgraders = upgraders or {}

    def put(self, record: R) -> Ref:
        """Save the record. Repeating the same record is a no-op; a different one is refused."""
        data = canonical_json(record.model_dump(mode="json"))
        path = self._path(record.id)
        if path.exists():
            if path.read_bytes() != data:
                raise RecordExists(f"{self._kind.value} id {record.id!r} holds a different record")
        else:
            self._write(path, data)
        return Ref(kind=self._kind, id=record.id, hash=hashlib.sha256(data).hexdigest())

    def get(self, record_id: str) -> R:
        path = self._path(record_id)
        try:
            raw = path.read_bytes()
        except FileNotFoundError:
            raise RecordMissing(self._kind.value, record_id) from None
        try:
            data = json.loads(raw)
        except ValueError:
            raise RecordCorrupt(self._kind.value, record_id, "not valid JSON") from None
        if not isinstance(data, dict):
            raise RecordCorrupt(self._kind.value, record_id, "not a JSON object")
        version = data.get("schema_version")
        if not isinstance(version, int) or isinstance(version, bool):
            raise RecordCorrupt(self._kind.value, record_id, "missing schema_version")
        if version > self._current_version:
            raise UnsupportedRecordVersion(
                self._kind.value, record_id, version, self._current_version
            )
        while version < self._current_version:
            upgrade = self._upgraders.get(version)
            if upgrade is None:
                raise UnsupportedRecordVersion(
                    self._kind.value, record_id, version, self._current_version
                )
            data = upgrade(data)
            version += 1
            data["schema_version"] = version
        try:
            record = self._model.model_validate(data)
        except ValidationError as error:
            raise RecordCorrupt(self._kind.value, record_id, error.errors()[0]["msg"]) from None
        if record.id != record_id:
            raise RecordCorrupt(self._kind.value, record_id, "id does not match the file name")
        return record

    def ids(self) -> list[str]:
        """Ids of every stored record, sorted."""
        if not self._folder.is_dir():
            return []
        return sorted(p.stem for p in self._folder.glob("*.json"))

    def verify(self, ref: Ref) -> None:
        """Raise unless the record exists and its bytes still hash to ``ref.hash``."""
        if ref.kind is not self._kind:
            raise ValueError(f"not a {self._kind.value} reference: {ref.kind.value}")
        try:
            raw = self._path(ref.id).read_bytes()
        except FileNotFoundError:
            raise RecordMissing(self._kind.value, ref.id) from None
        if hashlib.sha256(raw).hexdigest() != ref.hash:
            raise RecordCorrupt(self._kind.value, ref.id, "content differs from the recorded hash")

    def _path(self, record_id: str) -> Path:
        check_artifact_id(record_id)
        return self._folder / f"{record_id}.json"
