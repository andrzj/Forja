import hashlib
import json
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from forja.core.artifacts.errors import (
    ArtifactCorrupt,
    ArtifactExists,
    ArtifactMissing,
    InputMismatch,
    SchemaNotDefined,
    UnsupportedArtifactVersion,
)
from forja.core.artifacts.llm_output import ChangeDeclaration
from forja.core.artifacts.models import (
    ARTIFACT_SCHEMA_VERSION,
    ArtifactHeader,
    ArtifactType,
    Assumption,
    Executor,
    InputRef,
    Producer,
    check_artifact_id,
)
from forja.core.artifacts.schemas import (
    AuthoredTestsBody,
    ChangeRecordBody,
    CriteriaBody,
    ExecutionSummaryBody,
    FindingsBody,
    TaskDefinitionBody,
)
from forja.core.atomic import atomic_write_bytes
from forja.core.events.models import Ref, RefKind, canonical_json
from forja.core.ids import new_id

# Body schema per artifact type. A type appears here only once its fields are agreed.
BODY_MODELS: Mapping[ArtifactType, type[BaseModel]] = {
    ArtifactType.FINDINGS: FindingsBody,
    ArtifactType.CRITERIA: CriteriaBody,
    ArtifactType.TEST_MANIFEST: AuthoredTestsBody,
    ArtifactType.CHANGE_DECLARATION: ChangeDeclaration,
    ArtifactType.CHANGE_RECORD: ChangeRecordBody,
    ArtifactType.EXECUTION_SUMMARY: ExecutionSummaryBody,
    ArtifactType.TASK_DEFINITION: TaskDefinitionBody,
}

# (type, version N) -> function turning {"header": ..., "body": ...} of version N into N+1.
ArtifactUpgrader = Callable[[dict[str, Any]], dict[str, Any]]


@dataclass(frozen=True)
class StoredArtifact:
    header: ArtifactHeader
    body: BaseModel


class ArtifactStore:
    """Artifacts of one run: bodies by content hash, headers by id.

    ``blobs/<sha256>`` holds the canonical JSON body; ``artifacts/<id>.json`` holds the header that
    points to it. The blob is written first, so a header never points to a body that was not saved.
    Reading verifies the hash, so a changed or missing file is reported, never trusted.
    """

    def __init__(
        self,
        root: Path,
        *,
        write: Callable[[Path, bytes], None] = atomic_write_bytes,
        upgraders: Mapping[tuple[ArtifactType, int], ArtifactUpgrader] | None = None,
    ) -> None:
        self._root = root
        self._write = write
        self._upgraders = upgraders or {}

    def put(
        self,
        *,
        artifact_type: ArtifactType,
        producer: Producer,
        body: BaseModel,
        executor: Executor | None = None,
        attempt_id: str | None = None,
        base_commit: str | None = None,
        inputs: Iterable[InputRef] = (),
        assumptions: Iterable[Assumption] = (),
        artifact_id: str | None = None,
    ) -> ArtifactHeader:
        """Save an artifact. Repeating the call with the same id and content is a no-op."""
        model = _body_model(artifact_type)
        if not isinstance(body, model):
            raise TypeError(f"{artifact_type.value} needs a {model.__name__} body")
        blob = canonical_json(body.model_dump(mode="json"))
        header = ArtifactHeader(
            id=check_artifact_id(new_id() if artifact_id is None else artifact_id),
            type=artifact_type,
            schema_version=ARTIFACT_SCHEMA_VERSION,
            producer=producer,
            executor=executor,
            attempt_id=attempt_id,
            base_commit=base_commit,
            content_hash=hashlib.sha256(blob).hexdigest(),
            inputs=tuple(inputs),
            assumptions=tuple(assumptions),
        )
        for ref in header.inputs:
            self._check_input(ref)

        existing = self._header_path(header.id)
        if existing.exists():
            if self._read_header(header.id) == header:
                return header
            raise ArtifactExists(f"artifact id {header.id!r} already holds a different artifact")

        blob_path = self._blob_path(header.content_hash)
        if not (blob_path.exists() and _sha256(blob_path.read_bytes()) == header.content_hash):
            self._write(blob_path, blob)
        self._write(existing, canonical_json(header.model_dump(mode="json")) + b"\n")
        return header

    def header(self, artifact_id: str) -> ArtifactHeader:
        return self._read_header(artifact_id)

    def get(self, artifact_id: str) -> StoredArtifact:
        """Header and body, after checking the body bytes against the header's hash."""
        header = self._read_header(artifact_id)
        blob = self._read_blob(header)
        try:
            record: dict[str, Any] = {
                "header": header.model_dump(mode="json"),
                "body": json.loads(blob),
            }
        except ValueError:
            raise ArtifactCorrupt(artifact_id, "body is not valid JSON") from None
        version = header.schema_version
        while version < ARTIFACT_SCHEMA_VERSION:
            upgrade = self._upgraders.get((header.type, version))
            if upgrade is None:
                raise UnsupportedArtifactVersion(artifact_id, version, ARTIFACT_SCHEMA_VERSION)
            record = upgrade(record)
            version += 1
        try:
            body = _body_model(header.type).model_validate(record["body"])
        except ValidationError as error:
            raise ArtifactCorrupt(artifact_id, f"body: {error.errors()[0]['msg']}") from None
        return StoredArtifact(header, body)

    def ref(self, header: ArtifactHeader) -> Ref:
        """The pointer events carry: id and content hash."""
        return Ref(kind=RefKind.ARTIFACT, id=header.id, hash=header.content_hash)

    def verify(self, ref: Ref) -> None:
        """Raise unless the referenced artifact exists and still has the recorded content."""
        if ref.kind is not RefKind.ARTIFACT:
            raise ValueError(f"not an artifact reference: {ref.kind.value}")
        header = self._read_header(ref.id)
        if header.content_hash != ref.hash:
            raise ArtifactCorrupt(ref.id, "content hash differs from the one recorded")
        self._read_blob(header)

    def _check_input(self, ref: InputRef) -> None:
        try:
            header = self._read_header(ref.artifact_id)
            self._read_blob(header)
        except (ArtifactMissing, ArtifactCorrupt) as error:
            raise InputMismatch(f"input {ref.artifact_id!r} cannot be used: {error}") from error
        if header.content_hash != ref.content_hash:
            raise InputMismatch(f"input {ref.artifact_id!r} has another content hash than declared")

    def _read_header(self, artifact_id: str) -> ArtifactHeader:
        check_artifact_id(artifact_id)
        path = self._header_path(artifact_id)
        try:
            raw = path.read_bytes()
        except FileNotFoundError:
            raise ArtifactMissing(artifact_id, "header") from None
        try:
            data = json.loads(raw)
        except ValueError:
            raise ArtifactCorrupt(artifact_id, "header is not valid JSON") from None
        version = data.get("schema_version") if isinstance(data, dict) else None
        if isinstance(version, int) and version > ARTIFACT_SCHEMA_VERSION:
            raise UnsupportedArtifactVersion(artifact_id, version, ARTIFACT_SCHEMA_VERSION)
        try:
            header = ArtifactHeader.model_validate(data)
        except ValidationError as error:
            raise ArtifactCorrupt(artifact_id, f"header: {error.errors()[0]['msg']}") from None
        if header.id != artifact_id:
            raise ArtifactCorrupt(artifact_id, "header id does not match its file name")
        return header

    def _read_blob(self, header: ArtifactHeader) -> bytes:
        try:
            blob = self._blob_path(header.content_hash).read_bytes()
        except FileNotFoundError:
            raise ArtifactMissing(header.id, "body") from None
        if _sha256(blob) != header.content_hash:
            raise ArtifactCorrupt(header.id, "body does not match its content hash")
        return blob

    def _header_path(self, artifact_id: str) -> Path:
        return self._root / "artifacts" / f"{artifact_id}.json"

    def _blob_path(self, content_hash: str) -> Path:
        return self._root / "blobs" / content_hash


def _body_model(artifact_type: ArtifactType) -> type[BaseModel]:
    try:
        return BODY_MODELS[artifact_type]
    except KeyError:
        raise SchemaNotDefined(f"no body schema is defined yet for {artifact_type.value}") from None


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
