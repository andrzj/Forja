from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from pydantic import JsonValue

from forja.core.artifacts import StoredArtifact
from forja.core.events.models import Ref
from forja.core.evidence import Evidence
from forja.core.gates.models import GateResult


@dataclass(frozen=True)
class EvidenceItem:
    """Evidence together with the reference that identifies it in events and decisions."""

    ref: Ref
    evidence: Evidence


@dataclass(frozen=True)
class ArtifactItem:
    ref: Ref
    stored: StoredArtifact


@dataclass(frozen=True)
class GateInput:
    """Everything a check may look at. It judges; it never writes to the worktree.

    ``values`` are the thresholds, commands and limits of this one check, taken from the policy.
    """

    worktree: Path
    commit: str
    task_id: str
    stage_id: str
    attempt_id: str
    base_evidence: tuple[EvidenceItem, ...] = ()
    attempt_evidence: tuple[EvidenceItem, ...] = ()
    artifacts: tuple[ArtifactItem, ...] = ()
    values: Mapping[str, JsonValue] = field(default_factory=dict)


class Check(Protocol):
    """A named detector. Gates (numbered, ordered) group one or more checks.

    ``requires`` lists the adapter capabilities the check needs; when one is missing the check is
    not run and its result is ``not_applicable``.
    """

    @property
    def id(self) -> str: ...

    @property
    def gate(self) -> int: ...

    @property
    def requires(self) -> frozenset[str]: ...

    async def evaluate(self, data: GateInput) -> GateResult: ...
