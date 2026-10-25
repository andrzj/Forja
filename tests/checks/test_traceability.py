"""Gate 13 for the specifier: elements and criteria lead to each other, and nothing is orphaned."""

import asyncio
from pathlib import Path

from forja.checks.traceability import TraceabilityCheck
from forja.core.artifacts.elements import elements_of
from forja.core.artifacts.llm_output import Criterion, CriterionLevel, LeftOut
from forja.core.gates import Approved, GateInput, Rejected

ELEMENTS = elements_of("- sorts by name\n- filters by tag\n- exports to CSV")


def criterion(number: int, *origin: str) -> Criterion:
    return Criterion(id=number, text=f"c{number}", level=CriterionLevel.UNIT, origin=origin)


def judge(criteria: list[Criterion], left_out: list[LeftOut] | None = None) -> object:
    data = GateInput(Path("."), "c" * 40, "t1", "t1-c", "t1-ca1")
    check = TraceabilityCheck(ELEMENTS, criteria, left_out or [])
    return asyncio.run(check.evaluate(data))


def test_every_element_with_a_criterion_passes() -> None:
    assert isinstance(judge([criterion(1, "E1", "E2"), criterion(2, "E3")]), Approved)


def test_an_element_may_have_more_than_one_criterion() -> None:
    assert isinstance(
        judge([criterion(1, "E1"), criterion(2, "E1"), criterion(3, "E2"), criterion(4, "E3")]),
        Approved,
    )


def test_an_element_with_no_criterion_is_named() -> None:
    result = judge([criterion(1, "E1"), criterion(2, "E3")])
    assert isinstance(result, Rejected)
    assert [f.target for f in result.findings] == ["E2"]
    assert "filters by tag" in result.findings[0].message


def test_a_criterion_from_an_element_that_does_not_exist_is_named() -> None:
    result = judge([criterion(1, "E1", "E2", "E3"), criterion(2, "E9")])
    assert isinstance(result, Rejected)
    assert [f.target for f in result.findings] == ["criterion 2"]
    assert "E9" in result.findings[0].message


def test_an_element_left_out_with_a_reason_is_not_rejected() -> None:
    left = LeftOut(element="E3", reason="needs a service", missing_evidence="which format")
    assert isinstance(judge([criterion(1, "E1", "E2")], [left]), Approved)


def test_leaving_out_an_element_that_does_not_exist_is_named() -> None:
    left = LeftOut(element="E7", reason="r", missing_evidence="m")
    result = judge([criterion(1, "E1", "E2", "E3")], [left])
    assert isinstance(result, Rejected)
    assert [f.target for f in result.findings] == ["E7"]


def test_a_left_out_element_becomes_an_assumption_with_its_reason() -> None:
    left = LeftOut(element="E3", reason="needs a service", missing_evidence="which format")
    assumption = left.as_assumption()
    assert assumption.statement == "input element E3 is not built"
    assert assumption.reason == "needs a service"
    assert assumption.missing_evidence == "which format"


def test_all_the_problems_are_found_at_once() -> None:
    result = judge([criterion(1, "E8")])
    assert isinstance(result, Rejected)
    assert sorted(f.target for f in result.findings) == ["E1", "E2", "E3", "criterion 1"]
