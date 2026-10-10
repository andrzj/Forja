"""The record of what was actually sent to a model, kept for audit."""

import hashlib
from collections import Counter
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from forja.core.artifacts.models import Executor, NonEmpty, Producer
from forja.core.atomic import atomic_write_bytes
from forja.core.events.models import Ref, RefKind, Sha256, Timestamp, canonical_json, format_time
from forja.core.records import Record, RecordCorrupt, RecordMissing, RecordStore
from forja.core.redaction.engine import DropReason, ItemKind, RedactedItem, RedactionResult

SENT_PACKAGE_SCHEMA_VERSION = 1


class DroppedEntry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: NonEmpty
    kind: ItemKind
    reason: DropReason


class SentPackage(Record):
    """Who got what, under which rules. It holds counts and names, never a masked value."""

    attempt_id: NonEmpty
    role: Producer
    executor: Executor | None
    package_hash: Sha256
    rules_version: NonEmpty
    settings_digest: Sha256
    item_count: int
    findings_by_rule: dict[str, int]
    dropped: tuple[DroppedEntry, ...]
    created_at: Timestamp


def canonical_package(items: tuple[RedactedItem, ...]) -> bytes:
    """The package exactly as sent: the redacted items in order, as canonical JSON."""
    return canonical_json(
        [{"kind": item.kind.value, "name": item.name, "content": item.content} for item in items]
    )


class SentPackageStore(RecordStore[SentPackage]):
    """``sent_packages/<id>.json`` is the record; ``<id>.package`` is the redacted content.

    The content is what the model received after redaction, so keeping it exposes nothing that
    was masked. The record's hash lets anyone confirm the content was not altered later.
    """

    def __init__(self, root: Path, **kwargs: object) -> None:
        super().__init__(
            root,
            folder="sent_packages",
            model=SentPackage,
            kind=RefKind.SENT_PACKAGE,
            current_version=SENT_PACKAGE_SCHEMA_VERSION,
            **kwargs,  # type: ignore[arg-type]
        )

    def save(
        self,
        record_id: str,
        *,
        attempt_id: str,
        role: Producer,
        executor: Executor | None,
        result: RedactionResult,
        settings_digest: str,
        created_at: datetime,
    ) -> Ref:
        content = canonical_package(result.items)
        atomic_write_bytes(self._folder / f"{record_id}.package", content)
        counts = Counter(finding.rule for finding in result.findings)
        return self.put(
            SentPackage(
                schema_version=SENT_PACKAGE_SCHEMA_VERSION,
                id=record_id,
                attempt_id=attempt_id,
                role=role,
                executor=executor,
                package_hash=hashlib.sha256(content).hexdigest(),
                rules_version=result.rules_version,
                settings_digest=settings_digest,
                item_count=len(result.items),
                findings_by_rule=dict(sorted(counts.items())),
                dropped=tuple(
                    DroppedEntry(name=d.name, kind=d.kind, reason=d.reason) for d in result.dropped
                ),
                created_at=format_time(created_at),
            )
        )

    def read_package(self, record_id: str) -> bytes:
        """The package as it was sent, checked against the hash in its record."""
        record = self.get(record_id)
        try:
            content = (self._folder / f"{record_id}.package").read_bytes()
        except FileNotFoundError:
            raise RecordMissing(self._kind.value, record_id) from None
        if hashlib.sha256(content).hexdigest() != record.package_hash:
            raise RecordCorrupt(
                self._kind.value, record_id, "the package differs from its recorded hash"
            )
        return content
