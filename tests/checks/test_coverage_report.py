"""A tool may name its own report directory (a run id), so the report is a pattern, and several
reports (one per test project) become one."""

from pathlib import Path

from forja.checks.coverage import merge_coverage, report_paths
from forja.core.reports.models import CoverageReport, FileCoverage


def covering(covered: set[int], missed: set[int], tests: dict[int, set[str]] | None = None):  # type: ignore[no-untyped-def]
    return FileCoverage(
        covered=frozenset(covered),
        missed=frozenset(missed),
        tests={line: frozenset(names) for line, names in (tests or {}).items()},
    )


def test_a_plain_path_is_the_one_report(tmp_path: Path) -> None:
    assert report_paths(tmp_path, ".cover/report.xml") == [tmp_path / ".cover/report.xml"]


def test_a_pattern_finds_the_report_of_every_run_directory(tmp_path: Path) -> None:
    for run in ("b", "a"):
        (tmp_path / ".cover" / run).mkdir(parents=True)
        (tmp_path / ".cover" / run / "report.xml").write_text("x", encoding="utf-8")
    (tmp_path / ".cover" / "a" / "other.txt").write_text("x", encoding="utf-8")

    assert report_paths(tmp_path, ".cover/*/report.xml") == [
        tmp_path / ".cover/a/report.xml",
        tmp_path / ".cover/b/report.xml",
    ]
    assert report_paths(tmp_path, ".nothing/*/report.xml") == []


def test_one_report_is_returned_as_it_is() -> None:
    only = CoverageReport({"a.cs": covering({1}, {2})})

    assert merge_coverage([only]) is only


def test_a_line_is_covered_if_any_report_covers_it_and_the_tests_add_up() -> None:
    first = CoverageReport(
        {"a.cs": covering({1}, {2, 3}, {1: {"t1"}}), "b.cs": covering({5}, set())}
    )
    second = CoverageReport({"a.cs": covering({2}, {1, 3}, {2: {"t2"}})})

    merged = merge_coverage([first, second])

    a = merged.of("a.cs")
    assert a is not None
    assert (a.covered, a.missed) == (frozenset({1, 2}), frozenset({3}))
    assert a.tests == {1: frozenset({"t1"}), 2: frozenset({"t2"})}
    assert merged.of("b.cs") is not None
