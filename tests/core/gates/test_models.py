import pytest
from pydantic import ValidationError

from forja.core.gates import (
    Approved,
    Finding,
    GateResult,
    Inconclusive,
    InconclusiveReason,
    Location,
    NotApplicable,
    Rejected,
)
from forja.core.gates.models import RESULT_ADAPTER


def test_the_four_results_round_trip_through_json_keeping_their_variant() -> None:
    results: list[GateResult] = [
        Approved(),
        Rejected(findings=(Finding(message="m", target="t", measured=12, limit=10),)),
        Inconclusive(reason=InconclusiveReason.TIMED_OUT, detail="gave up", tool_run_ids=("r1",)),
        NotApplicable(missing_capability="mutation"),
    ]

    for result in results:
        again = RESULT_ADAPTER.validate_json(RESULT_ADAPTER.dump_json(result))
        assert again == result
        assert type(again) is type(result)


def test_an_unknown_result_name_is_rejected() -> None:
    with pytest.raises(ValidationError):
        RESULT_ADAPTER.validate_python({"result": "maybe"})


def test_a_rejection_must_carry_at_least_one_finding() -> None:
    with pytest.raises(ValidationError, match="at least 1"):
        Rejected(findings=())


def test_findings_need_a_message_and_a_target_and_finite_numbers() -> None:
    with pytest.raises(ValidationError):
        Finding(message="", target="t")
    with pytest.raises(ValidationError):
        Finding(message="m", target=" ")
    with pytest.raises(ValidationError):
        Finding(message="m", target="t", measured=float("nan"))
    with pytest.raises(ValidationError):
        Finding(message="m", target="t", limit=float("inf"))


def test_a_location_stays_inside_the_repository() -> None:
    assert str(Location(path="src/a.py", line=3)) == "src/a.py:3"
    assert str(Location(path="src/a.py")) == "src/a.py"
    for bad in ("../a.py", "/a.py", "C:/a.py"):
        with pytest.raises(ValidationError):
            Location(path=bad)
    with pytest.raises(ValidationError):
        Location(path="a.py", line=0)


def test_feedback_for_the_next_attempt_names_what_where_and_how_much() -> None:
    rejected = Rejected(
        findings=(
            Finding(
                message="complexity above the limit",
                target="src/a.py::parse",
                location=Location(path="src/a.py", line=40),
                measured=14,
                limit=10,
            ),
            Finding(message="new import cycle", target="pkg.a -> pkg.b"),
        )
    )

    assert rejected.feedback().splitlines() == [
        "complexity above the limit [src/a.py::parse at src/a.py:40] measured 14, limit 10",
        "new import cycle [pkg.a -> pkg.b]",
    ]


def test_the_reasons_for_an_inconclusive_result_are_a_closed_set() -> None:
    assert {r.value for r in InconclusiveReason} == {
        "tool_failed",
        "timed_out",
        "unsupported_construct",
    }
    with pytest.raises(ValidationError):
        Inconclusive.model_validate({"reason": "other", "detail": "x"})
    with pytest.raises(ValidationError):
        Inconclusive(reason=InconclusiveReason.TOOL_FAILED, detail="")


def test_results_reject_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs"):
        Approved.model_validate({"result": "approved", "score": 1})


def test_models_are_frozen_and_refuse_unknown_fields() -> None:
    from forja.core.gates.models import _strict

    # The models read this at import time, so only a direct call can notice a change to it.
    assert _strict() == {"frozen": True, "extra": "forbid"}


def test_a_finding_is_described_with_what_it_measured_only_when_it_measured() -> None:
    bare = Finding(message="too complex", target="a.py::f")
    located = Finding(
        message="too complex", target="a.py::f", location=Location(path="a.py", line=3)
    )
    measured_only = Finding(message="too complex", target="a.py::f", measured=12)
    limit_only = Finding(message="too complex", target="a.py::f", limit=10)
    both = Finding(message="too complex", target="a.py::f", measured=12.5, limit=10)

    assert bare.describe() == "too complex [a.py::f]"
    assert located.describe() == "too complex [a.py::f at a.py:3]"
    assert measured_only.describe() == "too complex [a.py::f] measured 12"
    assert limit_only.describe() == "too complex [a.py::f]"
    assert both.describe() == "too complex [a.py::f] measured 12.5, limit 10"
