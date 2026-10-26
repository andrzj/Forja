"""The package metrics check: a touched directory far from the main sequence is rejected."""

import asyncio
from pathlib import Path

from forja.checks.architecture.compare import Snapshot
from forja.checks.package_metrics import PackageMetricsCheck
from forja.checks.specs import default_registry
from forja.core.gates import GateInput, InconclusiveReason, Mode
from forja.core.gates.models import Approved, GateResult, Inconclusive, Rejected

THREE = "class A: ...\nclass B: ...\nclass C: ...\n"  # concrete types
ABSTRACT = "from abc import ABC\nclass A(ABC): ...\nclass B(ABC): ...\nclass C(ABC): ...\n"
STORE = "store/__init__.py"


def judge(
    before: dict[str, str],
    after: dict[str, str],
    changed: tuple[str, ...],
    **thresholds: float,
) -> GateResult:
    check = PackageMetricsCheck(Snapshot("python", before), Snapshot("python", after), changed)
    values = {"thresholds": {"python": thresholds}} if thresholds else {}
    data = GateInput(Path("."), "c" * 40, "t", "s", "a", values=values)  # type: ignore[arg-type]
    return asyncio.run(check.evaluate(data))


def used_by_cli(store: str) -> dict[str, str]:
    """``store`` is imported by ``cli`` and imports nothing: stable, so ``D = 1 - A``."""
    return {"cli/__init__.py": "import store\n", STORE: store}


def test_the_check_belongs_to_gate_9_in_observation_and_premises_when_it_cannot_measure() -> None:
    spec = default_registry().get("package_metrics")

    assert (spec.gate, spec.default_mode, spec.default_on_inconclusive.value) == (
        9,
        Mode.OBSERVATION,
        "premise",
    )
    assert spec.thresholds == frozenset({"max_distance", "min_types"})


def test_a_new_stable_concrete_directory_is_rejected_with_its_distance() -> None:
    before = {"cli/__init__.py": ""}
    after = used_by_cli(THREE)

    result = judge(before, after, (STORE,))

    assert isinstance(result, Rejected)
    (finding,) = result.findings
    assert finding.message == "package is far from the main sequence"
    assert (finding.target, finding.measured, finding.limit) == ("store", 1.0, 0.8)


def test_a_stable_abstract_directory_sits_on_the_main_sequence() -> None:
    result = judge({"cli/__init__.py": ""}, used_by_cli(ABSTRACT), (STORE,))

    assert isinstance(result, Approved)


def test_a_distance_that_was_already_over_the_limit_and_did_not_grow_passes() -> None:
    before = used_by_cli(THREE)
    after = used_by_cli(THREE + "class D: ...\n")

    assert isinstance(judge(before, after, (STORE,)), Approved)


def test_a_distance_over_the_limit_that_grew_is_rejected() -> None:
    mixed = "from abc import ABC\nclass A(ABC): ...\nclass B: ...\nclass C: ...\n"
    before = used_by_cli(mixed)  # A = 1/3, D = 2/3 is under the limit
    after = used_by_cli(THREE)  # A = 0, D = 1

    result = judge(before, after, (STORE,))

    assert isinstance(result, Rejected)
    assert result.findings[0].target == "store"


def test_a_distance_that_shrank_but_is_still_over_the_limit_passes() -> None:
    before = used_by_cli(THREE)  # D = 1
    after = used_by_cli("from abc import ABC\nclass A(ABC): ...\nclass B: ...\nclass C: ...\n")

    assert isinstance(judge(before, after, (STORE,), max_distance=0.5), Approved)


def test_a_directory_with_fewer_types_than_the_least_is_left_alone() -> None:
    result = judge({"cli/__init__.py": ""}, used_by_cli("class A: ...\nclass B: ...\n"), (STORE,))

    assert isinstance(result, Approved)


def test_the_policy_sets_both_limits() -> None:
    two = used_by_cli("class A: ...\nclass B: ...\n")

    assert isinstance(judge({"cli/__init__.py": ""}, two, (STORE,), min_types=2), Rejected)
    assert isinstance(
        judge({"cli/__init__.py": ""}, used_by_cli(THREE), (STORE,), max_distance=1), Approved
    )


def test_a_directory_the_attempt_did_not_touch_is_not_judged() -> None:
    before = {"cli/__init__.py": "", STORE: THREE}
    after = used_by_cli(THREE)  # store went from unused to used: its D grew, but it was not touched

    assert isinstance(judge(before, after, ("cli/__init__.py",)), Approved)


def test_nothing_changed_in_a_language_that_is_read_is_approved() -> None:
    assert isinstance(judge(used_by_cli(THREE), used_by_cli(THREE), ("README.md",)), Approved)
    assert isinstance(judge(used_by_cli(THREE), {"cli/__init__.py": ""}, (STORE,)), Approved)


def test_a_changed_file_that_does_not_parse_is_inconclusive() -> None:
    result = judge({}, used_by_cli("class (:\n"), (STORE,))

    assert isinstance(result, Inconclusive)
    assert result.reason is InconclusiveReason.UNSUPPORTED_CONSTRUCT


def test_a_parent_commit_with_nothing_readable_makes_every_touched_directory_new() -> None:
    result = judge({}, used_by_cli(THREE), (STORE,))

    assert isinstance(result, Rejected)
