"""The CRAP check: the arithmetic first, then the verdicts over a small project with fake tools."""

import asyncio
from pathlib import Path

from forja.checks.changes import read_before, read_changes
from forja.checks.complexity import Function, parse_spans
from forja.checks.coverage import CoverageShare
from forja.checks.crap import (
    DEFAULT_MAX_CRAP,
    CrapCheck,
    coverage_of,
    crap,
    max_crap,
)
from forja.core.gates import GateInput
from forja.core.gates.models import Approved, GateResult, Rejected
from forja.core.reports.models import CoverageReport, FileCoverage
from forja.core.states import Level
from tests.checks.support import Scene, deep, sinks

MOD = "src/sample/mod.py"


def gate_input(**values: object) -> GateInput:
    return GateInput(Path("."), "c" * 40, "t", "s", "a", values=values)  # type: ignore[arg-type]


def test_a_fully_tested_function_scores_its_complexity_and_an_untested_one_much_more() -> None:
    assert crap(5, 1.0) == 5
    assert crap(5, 0.0) == 30
    assert crap(5, 0.5) == 8.125


def test_the_limit_is_30_unless_the_policy_gives_a_positive_number() -> None:
    assert max_crap(gate_input(), "python") == DEFAULT_MAX_CRAP == 30.0
    assert max_crap(gate_input(thresholds={"python": {"max_crap": 12}}), "python") == 12.0
    assert max_crap(gate_input(thresholds={"python": {"max_crap": 0}}), "python") == 30.0
    assert max_crap(gate_input(thresholds={"python": {"max_crap": True}}), "python") == 30.0


def test_coverage_is_taken_over_the_lines_of_the_function() -> None:
    report = CoverageReport(
        {"a.py": FileCoverage(covered=frozenset({2, 3}), missed=frozenset({4, 9}))}
    )

    assert coverage_of(report, "a.py", Function(3, 1, 5)) == 2 / 3  # line 9 is another function
    assert coverage_of(report, "a.py", Function(1, 6, 8)) == 1.0  # nothing executable to test
    assert coverage_of(report, "b.py", Function(1, 1, 2)) == 0.0  # a file the tool never saw


def test_lizard_rows_give_the_place_of_each_function_and_keep_the_worst_of_a_name() -> None:
    rows = [
        '3,4,9,1,5,"f@1-5@a.py","a.py","f","f( )",1,5',
        '3,7,9,1,5,"f@8-12@a.py","a.py","f","f( )",8,12',
    ]

    assert parse_spans(rows) == {("a.py", "f"): Function(7, 8, 12)}


def judge(scene: Scene, report: CoverageReport | None) -> GateResult:
    git = scene.repo.git.at(scene.repo.path)
    changes = asyncio.run(read_changes(git))
    before = asyncio.run(read_before(git, changes, (".py",)))
    tools = scene.measurer._tools(sinks, Level.ATTEMPT, "a")  # noqa: SLF001
    check = CrapCheck(
        tools,
        scene.adapter,
        scene.repo.path,
        changes,
        (MOD,),
        before,
        scene.lizard,
        share=CoverageShare(report),
    )
    return asyncio.run(check.evaluate(gate_input()))


def covering(first: int, last: int, *, missed: bool = False) -> CoverageReport:
    lines = frozenset(range(first, last + 1))
    return CoverageReport(
        {MOD: FileCoverage(frozenset(), lines) if missed else FileCoverage(lines)}
    )


def test_a_new_complex_function_the_tests_do_not_run_is_rejected_with_its_score(
    scene: Scene,
) -> None:
    scene.write(MOD, deep("branchy", 9))

    result = judge(scene, covering(1, 20, missed=True))

    assert isinstance(result, Rejected)
    (finding,) = result.findings
    assert (finding.target, finding.measured, finding.limit) == (f"{MOD}::branchy", 110.0, 30.0)


def test_the_same_function_run_by_the_tests_is_approved(scene: Scene) -> None:
    scene.write(MOD, deep("branchy", 9))

    assert isinstance(judge(scene, covering(1, 20)), Approved)


def test_a_simple_function_needs_no_coverage_at_all(scene: Scene) -> None:
    scene.write(MOD, "def add(a: int, b: int) -> int:\n    return a + b\n\n\nX = 1\n")

    assert isinstance(judge(scene, None), Approved)  # the share is empty: a coverage run would fail


def test_an_old_function_that_did_not_get_worse_is_not_reproved(scene: Scene) -> None:
    scene.write(MOD, deep("branchy", 9))
    scene.repo.sh("add", "-A")
    scene.repo.sh("commit", "-m", "old debt")
    scene.write(MOD, deep("branchy", 9) + "\n\nX = 1\n")

    assert isinstance(judge(scene, covering(1, 20, missed=True)), Approved)


def test_an_old_function_that_got_more_complex_is_reproved(scene: Scene) -> None:
    scene.write(MOD, deep("branchy", 9))
    scene.repo.sh("add", "-A")
    scene.repo.sh("commit", "-m", "old debt")
    scene.write(MOD, deep("branchy", 10))

    assert isinstance(judge(scene, covering(1, 30, missed=True)), Rejected)
