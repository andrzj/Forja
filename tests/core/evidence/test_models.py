from typing import Any

import pytest
from pydantic import ValidationError

from forja.core.evidence import Evidence, MeasurementContext

CONTEXT: dict[str, Any] = {
    "tool": "lizard",
    "tool_version": "1.17.10",
    "config_hash": "cfg-9f2",
    "toolchain": "python",
    "toolchain_version": "3.12.4",
    "platform": "windows-AMD64",
    "scope": ["src/b.py", "src/a.py"],
    "commit": "c" * 40,
    "policy_version": "2026.10",
}


def evidence(**changes: Any) -> Evidence:
    data: dict[str, Any] = {
        "schema_version": 1,
        "id": "ev1",
        "measurement": "cyclomatic_complexity",
        "target": {"kind": "symbol", "id": "src/a.py::parse"},
        "value": 7,
        "unit": "count",
        "tool_run_id": "run1",
        "measured_at": "2026-10-10T12:00:00.000000Z",
        "context": CONTEXT,
    }
    data.update(changes)
    return Evidence.model_validate(data)


def test_evidence_carries_everything_the_spec_lists() -> None:
    e = evidence()

    assert (e.measurement, e.target.kind.value, e.value, e.unit) == (
        "cyclomatic_complexity",
        "symbol",
        7,
        "count",
    )
    assert e.tool_run_id == "run1"
    ctx = e.context
    assert (ctx.tool, ctx.tool_version, ctx.config_hash) == ("lizard", "1.17.10", "cfg-9f2")
    assert (ctx.toolchain, ctx.toolchain_version, ctx.platform) == (
        "python",
        "3.12.4",
        "windows-AMD64",
    )
    assert (ctx.commit, ctx.policy_version) == ("c" * 40, "2026.10")


@pytest.mark.parametrize("value", [True, False, 0, 7, 2.5, "ok"])
def test_the_value_keeps_its_type_through_json(value: object) -> None:
    again = Evidence.model_validate_json(evidence(value=value).model_dump_json())

    assert again.value == value
    assert type(again.value) is type(value)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_a_value_that_is_not_a_finite_number_is_rejected(value: float) -> None:
    with pytest.raises(ValidationError, match="finite"):
        evidence(value=value)


def test_scope_is_sorted_and_without_duplicates_so_order_never_matters() -> None:
    reordered = {**CONTEXT, "scope": ["src/a.py", "src/b.py"]}

    assert evidence().context == evidence(context=reordered).context
    assert evidence().context.scope == ("src/a.py", "src/b.py")
    with pytest.raises(ValidationError, match="unique"):
        evidence(context={**CONTEXT, "scope": ["a", "a"]})


@pytest.mark.parametrize(
    ("field", "bad"),
    [
        ("platform", "windows"),
        ("platform", "win dows-AMD64"),
        ("commit", "HEAD"),
        ("commit", "C" * 40),
        ("tool", ""),
        ("config_hash", " "),
    ],
)
def test_context_fields_are_validated(field: str, bad: str) -> None:
    with pytest.raises(ValidationError):
        MeasurementContext.model_validate({**CONTEXT, field: bad})


@pytest.mark.parametrize(
    "changes",
    [
        {"unit": ""},
        {"measurement": ""},
        {"target": {"kind": "folder", "id": "x"}},
        {"target": {"kind": "file", "id": ""}},
        {"measured_at": "yesterday"},
        {"tool_run_id": "../x"},
        {"id": "a/b"},
    ],
)
def test_other_fields_are_validated(changes: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        evidence(**changes)


def test_evidence_never_holds_a_gate_decision() -> None:
    with pytest.raises(ValidationError, match="Extra inputs"):
        evidence(decision="approved")
