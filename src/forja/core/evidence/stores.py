from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from forja.core.atomic import atomic_write_bytes
from forja.core.events.models import Ref, RefKind
from forja.core.evidence.models import (
    EVIDENCE_SCHEMA_VERSION,
    TOOL_RUN_SCHEMA_VERSION,
    Evidence,
    ToolRun,
)
from forja.core.process import Outcome, ProcessResult, ProcessSpec
from forja.core.records import RecordError, RecordMissing, RecordStore

Upgraders = Mapping[int, Callable[[dict[str, Any]], dict[str, Any]]]


class EvidenceNotAllowed(RecordError):
    """The tool run behind the evidence is unknown or did not finish, so it can prove nothing."""


class ToolRunStore(RecordStore[ToolRun]):
    def __init__(
        self,
        root: Path,
        *,
        write: Callable[[Path, bytes], None] = atomic_write_bytes,
        upgraders: Upgraders | None = None,
    ) -> None:
        super().__init__(
            root,
            folder="tool_runs",
            model=ToolRun,
            kind=RefKind.TOOL_RUN,
            current_version=TOOL_RUN_SCHEMA_VERSION,
            write=write,
            upgraders=upgraders,
        )

    def record(
        self, record_id: str, operation_id: str, spec: ProcessSpec, result: ProcessResult
    ) -> Ref:
        """Save what the runner reported; the returned reference goes into the effect event."""
        return self.put(ToolRun.from_result(record_id, operation_id, spec, result))


class EvidenceStore(RecordStore[Evidence]):
    """Evidence only exists for tool runs that ran to the end.

    A run that timed out, was cancelled or never started produces no evidence, so the gate sees
    an inconclusive measurement instead of a number nobody measured. Whether a non-zero exit code
    is still a valid measurement (a linter that exits 1 when it finds something) is the adapter's
    call, not the store's.
    """

    def __init__(
        self,
        root: Path,
        tool_runs: ToolRunStore,
        *,
        write: Callable[[Path, bytes], None] = atomic_write_bytes,
        upgraders: Upgraders | None = None,
    ) -> None:
        super().__init__(
            root,
            folder="evidence",
            model=Evidence,
            kind=RefKind.EVIDENCE,
            current_version=EVIDENCE_SCHEMA_VERSION,
            write=write,
            upgraders=upgraders,
        )
        self._tool_runs = tool_runs

    def put(self, record: Evidence) -> Ref:
        try:
            run = self._tool_runs.get(record.tool_run_id)
        except RecordMissing:
            raise EvidenceNotAllowed(f"unknown tool run {record.tool_run_id!r}") from None
        if run.outcome is not Outcome.EXITED:
            raise EvidenceNotAllowed(
                f"tool run {run.id!r} ended as {run.outcome.value}; it cannot produce evidence"
            )
        return super().put(record)
