"""The mutation check: pure pieces first, then the real thing over a small project."""

import asyncio
from pathlib import Path

import pytest

from forja.checks import mutation
from forja.checks.mutation import (
    DEFAULT_MIN_SCORE,
    MutationCheck,
    build_mutants,
    min_score,
    worker_count,
)
from forja.core.gates import GateInput
from forja.core.gates.models import Approved, Rejected
from forja.core.reports.models import CoverageReport, FileCoverage
from forja.core.states import Level
from tests.checks.support import Scene, sinks
from tests.core.idempotency.conftest import Repo

pytest.importorskip("coverage")


def gate_input(**values: object) -> GateInput:
    return GateInput(Path("."), "c" * 40, "t", "s", "a", values=values)  # type: ignore[arg-type]


def test_the_default_limit_is_65_percent_and_the_policy_may_change_it() -> None:
    assert min_score(gate_input(), "python") == DEFAULT_MIN_SCORE == 0.65
    assert min_score(gate_input(thresholds={"python": {"min_score": 0.8}}), "python") == 0.8
    assert min_score(gate_input(thresholds={"python": {"min_score": 7}}), "python") == 0.65
    assert min_score(gate_input(thresholds={"python": {"min_score": True}}), "python") == 0.65


def test_workers_come_from_the_policy_only_when_positive() -> None:
    assert worker_count(gate_input()) is None
    assert worker_count(gate_input(limits={"workers": 2})) == 2
    assert worker_count(gate_input(limits={"workers": 0})) is None


def test_a_test_file_is_the_part_of_a_context_before_the_double_colon() -> None:
    assert mutation.test_file("tests/test_a.py::test_x") == "tests/test_a.py"
    assert mutation.test_file("tests\\test_a.py::T::test_x") == "tests/test_a.py"
    assert mutation.test_file("test_x") is None


def test_a_covered_line_without_a_named_test_falls_back_to_every_test_file() -> None:
    coverage = FileCoverage(covered=frozenset({1, 2}), tests={1: frozenset({"t/a.py::x"})})

    assert mutation.tests_for(coverage, 1, ("t/a.py", "t/b.py")) == ("t/a.py",)
    assert mutation.tests_for(coverage, 2, ("t/a.py", "t/b.py")) == ("t/a.py", "t/b.py")
    assert mutation.tests_for(coverage, 3, ("t/a.py",)) == ()
    assert mutation.tests_for(None, 1, ("t/a.py",)) == ()


def test_only_the_lines_a_file_gained_are_mutated(tmp_path: Path) -> None:
    (tmp_path / "m.py").write_text("def f(a, b):\n    x = a + b\n    return a - b\n")
    coverage = CoverageReport(
        {"m.py": FileCoverage(covered=frozenset({2, 3}), tests={2: frozenset({"t/t.py::a"})})}
    )

    mutants = build_mutants(tmp_path, {"m.py": frozenset({3})}, coverage)

    assert [(m.line, m.change) for m in mutants] == [(3, "- -> +")]
    assert mutants[0].tests == ("t/t.py",)


def judge(scene: Scene) -> object:
    from forja.checks.changes import read_changes  # noqa: PLC0415

    git = scene.repo.git.at(scene.repo.path)
    changes = asyncio.run(read_changes(git))
    tools = scene.measurer._tools(sinks, Level.ATTEMPT, "a")  # noqa: SLF001
    check = MutationCheck(
        tools,
        scene.adapter,
        scene.repo.path,
        changes,
        ("src/sample/mod.py",),
        scene.repo.env,
    )
    return asyncio.run(check.evaluate(gate_input()))


@pytest.mark.slow
def test_a_new_line_the_tests_check_is_approved(repo: Repo, tmp_path: Path) -> None:
    scene = Scene(repo, tmp_path, real=True)
    scene.write(
        "src/sample/mod.py",
        "def add(a: int, b: int) -> int:\n    return a + b\n\n\n"
        "def sub(a: int, b: int) -> int:\n    return a - b\n",
    )
    scene.write(
        "tests/test_mod.py",
        "from sample.mod import add, sub\n\n\n"
        "def test_add() -> None:\n    assert add(1, 2) == 3\n\n\n"
        "def test_sub() -> None:\n    assert sub(3, 1) == 2\n",
    )

    assert isinstance(judge(scene), Approved)


@pytest.mark.slow
def test_a_new_line_no_test_checks_is_rejected_with_the_score(repo: Repo, tmp_path: Path) -> None:
    scene = Scene(repo, tmp_path, real=True)
    scene.write(
        "src/sample/mod.py",
        "def add(a: int, b: int) -> int:\n    return a + b\n\n\n"
        "def sub(a: int, b: int) -> int:\n    return a - b\n",
    )

    result = judge(scene)

    assert isinstance(result, Rejected)
    assert result.findings[0].measured == 0.0
    assert result.findings[0].limit == 0.65
    assert any(f.target == "src/sample/mod.py:6" for f in result.findings)
