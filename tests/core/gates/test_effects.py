"""The mode x policy x result matrix, written out by hand from the spec."""

import pytest

from forja.core.gates import (
    STOPPING_EFFECTS,
    Approved,
    CheckSettings,
    Effect,
    GateResult,
    InconclusivePolicy,
    InvalidCheckSettings,
    Mode,
    NotApplicable,
    decide_effect,
)
from tests.core.gates.support import INCONCLUSIVE, REJECTED

E = Effect
RESULTS: dict[str, GateResult] = {
    "approved": Approved(),
    "not_applicable": NotApplicable(missing_capability="mutation"),
    "rejected": REJECTED,
    "inconclusive": INCONCLUSIVE,
}

# (mode, on_inconclusive) -> effect per result
MATRIX = {
    (Mode.BLOCKING, InconclusivePolicy.BLOCK): {
        "approved": E.PASS,
        "not_applicable": E.PASS,
        "rejected": E.REJECT_ATTEMPT,
        "inconclusive": E.BLOCK_TASK,
    },
    (Mode.BLOCKING, InconclusivePolicy.PREMISE): {
        "approved": E.PASS,
        "not_applicable": E.PASS,
        "rejected": E.REJECT_ATTEMPT,
        "inconclusive": E.CONTINUE_WITH_ASSUMPTION,
    },
    **{
        (Mode.OBSERVATION, policy): {
            "approved": E.PASS,
            "not_applicable": E.PASS,
            "rejected": E.REPORT_ONLY,
            "inconclusive": E.REPORT_ONLY,
        }
        for policy in (None, InconclusivePolicy.BLOCK, InconclusivePolicy.PREMISE)
    },
}

CASES = [
    pytest.param(mode, policy, name, expected, id=f"{mode.value}/{policy}/{name}")
    for (mode, policy), row in MATRIX.items()
    for name, expected in row.items()
]


@pytest.mark.parametrize(("mode", "policy", "result", "expected"), CASES)
def test_effect_follows_the_spec_matrix(
    mode: Mode, policy: InconclusivePolicy | None, result: str, expected: Effect
) -> None:
    assert decide_effect(CheckSettings(mode, policy), RESULTS[result]) is expected


def test_observation_never_stops_anything() -> None:
    for policy in (None, *InconclusivePolicy):
        for result in RESULTS.values():
            effect = decide_effect(CheckSettings(Mode.OBSERVATION, policy), result)
            assert effect not in STOPPING_EFFECTS


def test_a_blocking_check_without_an_inconclusive_policy_is_refused() -> None:
    with pytest.raises(InvalidCheckSettings, match="on_inconclusive"):
        CheckSettings(Mode.BLOCKING)


def test_an_observation_check_may_carry_a_policy_for_its_promotion() -> None:
    assert CheckSettings(Mode.OBSERVATION).on_inconclusive is None
    assert CheckSettings(Mode.OBSERVATION, InconclusivePolicy.PREMISE).mode is Mode.OBSERVATION


def test_only_rejecting_the_attempt_or_blocking_the_task_stop_the_sequence() -> None:
    assert {Effect.REJECT_ATTEMPT, Effect.BLOCK_TASK} == STOPPING_EFFECTS
