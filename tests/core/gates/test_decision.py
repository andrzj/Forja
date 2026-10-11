import asyncio
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from forja.core.events import RefKind
from forja.core.events.models import Ref
from forja.core.evidence import cache_key
from forja.core.gates import (
    Approved,
    Effect,
    GateDecision,
    GateDecisionStore,
    GatePipeline,
    Mode,
    build_decision,
)
from forja.core.gates.models import RESULT_ADAPTER
from forja.core.records import RecordCorrupt
from tests.core.events.support import RUN, create_run, open_log
from tests.core.evidence.test_models import CONTEXT
from tests.core.gates.support import (
    BLOCKING,
    REJECTED,
    FakeCheck,
    evidence_item,
    evidence_ref,
    make_input,
)

MOMENT = datetime(2026, 10, 10, 12, 0, tzinfo=UTC)


def decision_for(
    tmp_path: Path, check: FakeCheck | None = None, **input_changes: Any
) -> GateDecision:
    check = check or FakeCheck("complexity", 8, REJECTED)
    data = make_input(tmp_path, **input_changes)
    outcome = asyncio.run(GatePipeline([check], {check.id: BLOCKING}).run(data, set()))
    return build_decision("dec1", outcome.runs[0], data, "0.0.0+abcdef123456", MOMENT)


def test_the_decision_records_the_judgment_the_policy_and_the_inputs(tmp_path: Path) -> None:
    base, attempt = evidence_item("ev-base"), evidence_item("ev-new", value=9)

    decision = decision_for(tmp_path, base_evidence=(base,), attempt_evidence=(attempt,))

    assert (decision.check_id, decision.policy_version) == ("complexity", "0.0.0+abcdef123456")
    assert (decision.mode, decision.on_inconclusive) == (Mode.BLOCKING, BLOCKING.on_inconclusive)
    assert decision.effect is Effect.REJECT_ATTEMPT
    assert decision.result == REJECTED
    assert (decision.task_id, decision.stage_id, decision.attempt_id) == ("t1", "s1", "a1")
    assert decision.commit == "d" * 40
    assert decision.base_evidence == (base.ref,) and decision.attempt_evidence == (attempt.ref,)
    assert decision.decided_at == "2026-10-10T12:00:00.000000Z"


def test_the_decision_lists_the_measurement_keys_it_relied_on_without_repeats(
    tmp_path: Path,
) -> None:
    same_key = (evidence_item("ev1"), evidence_item("ev2"))
    other = evidence_item("ev3", context={**CONTEXT, "tool": "radon"})

    decision = decision_for(tmp_path, base_evidence=same_key, attempt_evidence=(other,))

    expected = sorted({cache_key(i.evidence.context) for i in (*same_key, other)})
    assert list(decision.cache_keys) == expected
    assert len(expected) == 2


def test_the_decision_copies_no_evidence_content(tmp_path: Path) -> None:
    decision = decision_for(tmp_path, attempt_evidence=(evidence_item("ev1", value=4242),))

    dumped = decision.model_dump_json()
    assert "4242" not in dumped
    assert '"id":"ev1"' in dumped.replace(" ", "")


def test_it_is_stored_immutably_and_referenced_by_id_and_hash(tmp_path: Path) -> None:
    store = GateDecisionStore(tmp_path / "run")
    decision = decision_for(tmp_path)

    ref = store.put(decision)

    assert (ref.kind, ref.id) == (RefKind.GATE_DECISION, "dec1")
    assert store.get("dec1") == decision
    assert type(store.get("dec1").result) is type(decision.result)
    store.verify(ref)
    assert store.put(decision) == ref
    path = tmp_path / "run" / "gate_decisions" / "dec1.json"
    path.write_bytes(path.read_bytes().replace(b"rejected", b"approved"))
    with pytest.raises(RecordCorrupt):
        store.verify(ref)


def test_an_effect_that_contradicts_the_result_is_refused(tmp_path: Path) -> None:
    good = decision_for(tmp_path).model_dump(mode="json")

    with pytest.raises(ValidationError, match="contradicts the result"):
        GateDecision.model_validate({**good, "effect": "pass"})
    with pytest.raises(ValidationError, match="contradicts the result"):
        GateDecision.model_validate(
            {**good, "result": RESULT_ADAPTER.dump_python(Approved()), "effect": "reject_attempt"}
        )


def test_a_blocking_decision_must_name_its_inconclusive_policy(tmp_path: Path) -> None:
    good = decision_for(tmp_path).model_dump(mode="json")

    with pytest.raises(ValidationError, match="on_inconclusive"):
        GateDecision.model_validate({**good, "on_inconclusive": None})


def test_references_must_be_of_the_kind_the_field_holds(tmp_path: Path) -> None:
    good = decision_for(tmp_path).model_dump(mode="json")
    wrong = Ref(kind=RefKind.ARTIFACT, id="art1", hash="b" * 64).model_dump(mode="json")

    with pytest.raises(ValidationError, match="evidence"):
        GateDecision.model_validate({**good, "base_evidence": [wrong]})
    with pytest.raises(ValidationError, match="artifact"):
        GateDecision.model_validate({**good, "artifacts": [evidence_ref().model_dump(mode="json")]})


def test_a_transition_event_can_cite_the_decision_that_caused_it(tmp_path: Path) -> None:
    from forja.core.states import ExecutionState, Level

    store = GateDecisionStore(tmp_path / "run")
    ref = store.put(decision_for(tmp_path))

    with open_log(tmp_path / "events.jsonl") as log:
        create_run(log)
        event = log.append_transition(
            Level.EXECUTION, RUN, ExecutionState.PREPARING, ExecutionState.CONFIRMED, refs=[ref]
        )

    assert event.refs == (ref,)


def test_the_decision_lists_the_artifacts_the_check_saw(tmp_path: Path) -> None:
    from typing import cast

    from forja.core.gates import ArtifactItem

    ref = Ref(kind=RefKind.ARTIFACT, id="art1", hash="b" * 64)
    item = ArtifactItem(ref=ref, stored=cast(Any, None))  # only the reference is recorded

    decision = decision_for(tmp_path, artifacts=(item,))

    assert decision.artifacts == (ref,)


def test_the_store_passes_its_options_on_to_the_record_store(tmp_path: Path) -> None:
    written: list[Path] = []

    def spy(path: Path, data: bytes) -> None:
        written.append(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    GateDecisionStore(tmp_path, write=spy).put(decision_for(tmp_path))

    assert [p.name for p in written] == ["dec1.json"]
