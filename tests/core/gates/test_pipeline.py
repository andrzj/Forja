import asyncio
from collections.abc import Mapping
from pathlib import Path

import pytest
from pydantic import JsonValue

from forja.core.gates import (
    Approved,
    Check,
    Effect,
    GatePipeline,
    NotApplicable,
    Verdict,
)
from tests.core.gates.support import (
    BLOCKING,
    BLOCKING_PREMISE,
    INCONCLUSIVE,
    OBSERVATION,
    REJECTED,
    CrashingCheck,
    FakeCheck,
    make_input,
)


def run(pipeline: GatePipeline, tmp_path: Path, capabilities: set[str] | None = None):  # type: ignore[no-untyped-def]
    return asyncio.run(pipeline.run(make_input(tmp_path), capabilities or set()))


def settings_for(*checks: FakeCheck, setting=BLOCKING):  # type: ignore[no-untyped-def]
    return {check.id: setting for check in checks}


def test_checks_run_in_gate_order_whatever_the_registration_order(tmp_path: Path) -> None:
    late = FakeCheck("late", 9, Approved())
    early = FakeCheck("early", 2, Approved())
    first_of_gate_5 = FakeCheck("five_a", 5, Approved())
    second_of_gate_5 = FakeCheck("five_b", 5, Approved())
    checks = [late, second_of_gate_5, early, first_of_gate_5]

    outcome = run(GatePipeline(checks, settings_for(*checks)), tmp_path)

    assert [r.check_id for r in outcome.runs] == ["early", "five_b", "five_a", "late"]
    assert outcome.verdict is Verdict.PASSED
    assert outcome.stopped_by is None


def test_a_rejection_stops_the_sequence_and_later_checks_do_not_run(tmp_path: Path) -> None:
    ok, bad, never = (
        FakeCheck("ok", 1, Approved()),
        FakeCheck("bad", 2, REJECTED),
        FakeCheck("never", 3, Approved()),
    )
    checks = [ok, bad, never]

    outcome = run(GatePipeline(checks, settings_for(*checks)), tmp_path)

    assert outcome.verdict is Verdict.REJECTED
    assert outcome.stopped_by is not None and outcome.stopped_by.check_id == "bad"
    assert [r.check_id for r in outcome.runs] == ["ok", "bad"]
    assert never.calls == []


def test_an_inconclusive_result_with_block_stops_and_blocks_the_task(tmp_path: Path) -> None:
    flaky, never = FakeCheck("flaky", 1, INCONCLUSIVE), FakeCheck("never", 2, Approved())
    checks = [flaky, never]

    outcome = run(GatePipeline(checks, settings_for(*checks)), tmp_path)

    assert outcome.verdict is Verdict.BLOCKED
    assert outcome.runs[0].effect is Effect.BLOCK_TASK
    assert never.calls == []


def test_an_inconclusive_result_with_premise_goes_on_and_is_listed_as_an_assumption(
    tmp_path: Path,
) -> None:
    flaky, after = FakeCheck("flaky", 1, INCONCLUSIVE), FakeCheck("after", 2, Approved())
    checks = [flaky, after]

    outcome = run(GatePipeline(checks, settings_for(*checks, setting=BLOCKING_PREMISE)), tmp_path)

    assert outcome.verdict is Verdict.PASSED
    assert [r.check_id for r in outcome.assumptions] == ["flaky"]
    assert len(after.calls) == 1


def test_observation_findings_are_reported_without_stopping_later_checks(tmp_path: Path) -> None:
    noisy, after = FakeCheck("noisy", 1, REJECTED), FakeCheck("after", 2, Approved())
    checks = [noisy, after]

    outcome = run(GatePipeline(checks, settings_for(*checks, setting=OBSERVATION)), tmp_path)

    assert outcome.verdict is Verdict.PASSED
    assert [r.check_id for r in outcome.reports] == ["noisy"]
    assert len(after.calls) == 1


def test_a_missing_capability_means_not_applicable_and_the_check_is_never_called(
    tmp_path: Path,
) -> None:
    needs = FakeCheck("mutation", 7, REJECTED, requires=frozenset({"mutation", "coverage"}))
    after = FakeCheck("after", 8, Approved())
    checks = [needs, after]

    outcome = run(GatePipeline(checks, settings_for(*checks)), tmp_path, {"coverage"})

    first = outcome.runs[0]
    assert first.result == NotApplicable(missing_capability="mutation")
    assert first.effect is Effect.PASS
    assert needs.calls == []
    assert outcome.verdict is Verdict.PASSED
    assert [r.check_id for r in outcome.reports] == ["mutation"]
    assert len(after.calls) == 1


def test_a_check_with_every_capability_is_evaluated(tmp_path: Path) -> None:
    needs = FakeCheck("mutation", 7, REJECTED, requires=frozenset({"mutation"}))

    outcome = run(GatePipeline([needs], settings_for(needs)), tmp_path, {"mutation", "extra"})

    assert outcome.verdict is Verdict.REJECTED
    assert len(needs.calls) == 1


def test_each_check_receives_only_its_own_policy_values(tmp_path: Path) -> None:
    a, b = FakeCheck("a", 1, Approved()), FakeCheck("b", 2, Approved())
    values: dict[str, Mapping[str, JsonValue]] = {"a": {"limits": {"max_files": 3}}}

    run(GatePipeline([a, b], settings_for(a, b), values), tmp_path)

    assert a.calls[0].values == {"limits": {"max_files": 3}}
    assert b.calls[0].values == {}
    assert a.calls[0].commit == b.calls[0].commit == "d" * 40


def test_an_empty_pipeline_passes(tmp_path: Path) -> None:
    assert run(GatePipeline([], {}), tmp_path).verdict is Verdict.PASSED


def test_a_crash_inside_a_check_is_a_bug_and_is_not_turned_into_a_result(tmp_path: Path) -> None:
    crashing: Check = CrashingCheck()

    with pytest.raises(RuntimeError, match="bug in the check"):
        run(GatePipeline([crashing], {"crash": BLOCKING}), tmp_path)


def test_the_configuration_of_the_pipeline_is_validated(tmp_path: Path) -> None:
    a = FakeCheck("a", 1, Approved())

    with pytest.raises(ValueError) as duplicated:
        GatePipeline([a, FakeCheck("a", 2, Approved())], {"a": BLOCKING})
    assert str(duplicated.value) == "check ids must be unique"
    with pytest.raises(ValueError, match="without settings"):
        GatePipeline([a], {})
    with pytest.raises(ValueError, match="start at 1"):
        GatePipeline([FakeCheck("zero", 0, Approved())], {"zero": BLOCKING})


def test_each_run_remembers_the_gate_number_of_its_check(tmp_path: Path) -> None:
    outcome = run(GatePipeline([FakeCheck("late", 7, Approved())], {"late": BLOCKING}), tmp_path)

    assert [(r.check_id, r.gate) for r in outcome.runs] == [("late", 7)]
