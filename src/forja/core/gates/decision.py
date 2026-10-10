"""The persisted record of one gate judgment (contract 4's `decisão de gate`)."""

from datetime import datetime
from pathlib import Path
from typing import Self

from pydantic import model_validator

from forja.core.artifacts.models import GitCommit, NonEmpty
from forja.core.events.models import Ref, RefKind, Sha256, Timestamp, format_time
from forja.core.evidence.cache import cache_key
from forja.core.gates.check import GateInput
from forja.core.gates.effects import CheckSettings, decide_effect
from forja.core.gates.models import Effect, GateResult, InconclusivePolicy, Mode
from forja.core.gates.pipeline import CheckRun
from forja.core.records import Record, RecordStore

GATE_DECISION_SCHEMA_VERSION = 1


class GateDecision(Record):
    """Which check judged what, under which policy, and what the judgment led to.

    It references its inputs by id and hash and never copies them. The evidence it judged
    contains no decision, so the two layers never point at each other. ``cache_keys`` lists the
    measurement keys behind the evidence it used, so reuse can be audited.
    """

    check_id: NonEmpty
    policy_version: NonEmpty
    mode: Mode
    on_inconclusive: InconclusivePolicy | None
    result: GateResult
    effect: Effect
    commit: GitCommit
    task_id: NonEmpty
    stage_id: NonEmpty
    attempt_id: NonEmpty
    base_evidence: tuple[Ref, ...] = ()
    attempt_evidence: tuple[Ref, ...] = ()
    artifacts: tuple[Ref, ...] = ()
    cache_keys: tuple[Sha256, ...] = ()
    decided_at: Timestamp

    @model_validator(mode="after")
    def _effect_follows_from_mode_policy_and_result(self) -> Self:
        expected = decide_effect(CheckSettings(self.mode, self.on_inconclusive), self.result)
        if self.effect is not expected:
            raise ValueError(
                f"effect {self.effect.value} contradicts the result; expected {expected.value}"
            )
        return self

    @model_validator(mode="after")
    def _references_have_the_right_kind(self) -> Self:
        for refs, kind in (
            (self.base_evidence, RefKind.EVIDENCE),
            (self.attempt_evidence, RefKind.EVIDENCE),
            (self.artifacts, RefKind.ARTIFACT),
        ):
            if any(ref.kind is not kind for ref in refs):
                raise ValueError(f"expected only {kind.value} references")
        return self


class GateDecisionStore(RecordStore[GateDecision]):
    def __init__(self, root: Path, **kwargs: object) -> None:
        super().__init__(
            root,
            folder="gate_decisions",
            model=GateDecision,
            kind=RefKind.GATE_DECISION,
            current_version=GATE_DECISION_SCHEMA_VERSION,
            **kwargs,  # type: ignore[arg-type]
        )


def build_decision(
    decision_id: str,
    run: CheckRun,
    data: GateInput,
    policy_version: str,
    decided_at: datetime,
) -> GateDecision:
    """Turn one check run and the input it saw into the record the transition event will cite."""
    items = (*data.base_evidence, *data.attempt_evidence)
    return GateDecision(
        schema_version=GATE_DECISION_SCHEMA_VERSION,
        id=decision_id,
        check_id=run.check_id,
        policy_version=policy_version,
        mode=run.settings.mode,
        on_inconclusive=run.settings.on_inconclusive,
        result=run.result,
        effect=run.effect,
        commit=data.commit,
        task_id=data.task_id,
        stage_id=data.stage_id,
        attempt_id=data.attempt_id,
        base_evidence=tuple(item.ref for item in data.base_evidence),
        attempt_evidence=tuple(item.ref for item in data.attempt_evidence),
        artifacts=tuple(item.ref for item in data.artifacts),
        cache_keys=tuple(sorted({cache_key(item.evidence.context) for item in items})),
        decided_at=format_time(decided_at),
    )
