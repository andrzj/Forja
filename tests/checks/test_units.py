"""Edges of the small functions: the cases where one character more or less changes the answer."""

import asyncio
import json
import sys
from pathlib import Path

import pytest

from forja.checks.base import Undecided, measure, measure_plan
from forja.checks.build_and_tests import BuildCheck, TestsCheck
from forja.checks.changes import (
    AddedLine,
    Change,
    ChangeKind,
    Changes,
    added_lines,
    count_lines,
    parse_status,
    unquote,
    write_files,
)
from forja.checks.complexity import max_ccn, parse_functions
from forja.checks.layout import FormatCheck, LintCheck, violations
from forja.checks.scope import ScopeCheck, in_scope
from forja.checks.secrets import UNPLACED, SecretsCheck
from forja.checks.tooling import Execution, Tools
from forja.core.adapters import (
    CommandPlan,
    EvidenceDraft,
    Operation,
    OperationRequest,
)
from forja.core.events import EventLog
from forja.core.evidence import Target, TargetKind
from forja.core.gates import (
    Approved,
    GateInput,
    Inconclusive,
    InconclusiveReason,
    NotApplicable,
    Rejected,
)
from forja.core.process import Outcome, ProcessResult
from forja.core.states import ExecutionState, Level
from forja.languages.python import PythonAdapter
from forja.orchestrator.ports import TaskInfo
from tests.checks.support import RUN, sinks
from tests.core.events.support import FakeClock


def data(values: dict | None = None) -> GateInput:  # type: ignore[type-arg]
    return GateInput(Path("."), "c" * 40, "t1", "t1-s", "t1-a1", values=values or {})


@pytest.fixture
def log(tmp_path: Path) -> EventLog:
    opened = EventLog.open(tmp_path / "events.jsonl", RUN, clock=FakeClock())
    opened.append_transition(Level.EXECUTION, RUN, None, ExecutionState.PREPARING)
    return opened


def tools(log: EventLog, tmp_path: Path) -> Tools:
    return Tools(
        sinks=sinks,
        log=log,
        level=Level.ATTEMPT,
        target="t1-a1",
        logs=tmp_path / "logs",
        host_env={},
    )


# -- the quoting git adds --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("quoted", "plain"),
    [
        ('""', ""),
        ('"a"', "a"),
        ('"ab"', "ab"),
        ('"\\""', '"'),
        ('"\\"x"', '"x'),
        ('"\\\\"', "\\"),
        ('"\\"', "\\"),
        ('"x\\n"', "x\n"),
        ('"\\n"', "\n"),
        ('"\\303\\251\\303\\251"', "éé"),
        ('"a\\303\\251b"', "aéb"),
        ('"\\303"', "�"),
        ('"\\q"', "\\q"),
        ('"é"', "é"),
    ],
)
def test_unquote_walks_the_name_one_piece_at_a_time(quoted: str, plain: str) -> None:
    assert unquote(quoted) == plain


# -- what git says about a change ------------------------------------------------------------------


def test_status_lines_are_split_on_tabs_and_nothing_else() -> None:
    assert parse_status(["M a.py", "A b.py", "M\ta b.py"]) == (
        Change(ChangeKind.MODIFIED, "a b.py"),
    )


def test_a_copy_needs_both_its_names_and_a_type_change_needs_one() -> None:
    assert parse_status(["C\tonly", "C100\tfrom\tto", "T\tlink", "T\ta\tb", "A\tx\ty"]) == (
        Change(ChangeKind.ADDED, "to"),
        Change(ChangeKind.MODIFIED, "link"),
    )


def test_the_size_counts_the_first_two_columns_even_when_the_name_has_a_tab() -> None:
    assert count_lines(["3\t1\ta\tb.py", "2\t0\tc.py"]) == 6


def test_added_lines_need_a_hunk_to_belong_to() -> None:
    assert added_lines(("@@ -0,0 +1 @@", "+x")) == [AddedLine(None, 1, "x")]
    assert added_lines(("+++ b/a.py", "+x")) == []


def test_a_header_for_the_null_device_leaves_the_added_lines_without_a_file() -> None:
    patch = ("+++ /dev/null", "@@ -0,0 +1 @@", "+x")

    assert added_lines(patch) == [AddedLine(None, 1, "x")]


def test_a_hunk_header_without_a_count_owes_one_line() -> None:
    patch = (
        "+++ b/a.py",
        "@@ -1 +4 @@",
        "-old",
        "+new",
        "+++ b/b.py",
        "@@ -1 +2,2 @@",
        "+one",
        "+two",
    )

    assert added_lines(patch) == [
        AddedLine("a.py", 4, "new"),
        AddedLine("b.py", 2, "one"),
        AddedLine("b.py", 3, "two"),
    ]


def test_the_lines_removed_between_hunks_do_not_end_the_next_one() -> None:
    patch = (
        "+++ b/a.py",
        "@@ -1,2 +1,2 @@",
        "-x",
        "-y",
        "+a",
        "+b",
        "-z",
        "+++ b/b.py",
        "@@ -1 +1 @@",
        "-q",
        "+c",
    )

    assert added_lines(patch) == [
        AddedLine("a.py", 1, "a"),
        AddedLine("a.py", 2, "b"),
        AddedLine("b.py", 1, "c"),
    ]


def test_files_are_written_where_they_belong_even_when_the_directory_is_shared(
    tmp_path: Path,
) -> None:
    write_files({"a/b/c.py": "one\n", "a/b/d.py": "two\n", "e.py": "three\n"}, tmp_path)

    assert (tmp_path / "a" / "b" / "c.py").read_bytes() == b"one\n"
    assert (tmp_path / "a" / "b" / "d.py").read_bytes() == b"two\n"
    assert (tmp_path / "e.py").read_bytes() == b"three\n"


# -- the limits ------------------------------------------------------------------------------------


def test_a_limit_of_one_is_a_limit() -> None:
    assert max_ccn(data({"thresholds": {"python": {"max_ccn": 1}}}), "python") == 1


def test_a_row_the_parser_cannot_read_does_not_stop_the_rows_after_it() -> None:
    lines = [
        "short,row",
        '2,x,7,1,2,"a@1-2@m.py","m.py","a","a()",1,2',
        '2,4,7,1,2,"b@3-4@m.py","m.py","b","b()",3,4',
    ]

    assert parse_functions(lines) == {("m.py", "b"): 4}


def test_format_and_lint_leave_files_that_are_not_python_alone() -> None:
    changes = Changes((Change(ChangeKind.MODIFIED, "README.md"),), 1, ())
    root = Path(".")
    for check in (
        FormatCheck(None, None, root, changes),  # type: ignore[arg-type]
        LintCheck(None, None, root, changes, {}),  # type: ignore[arg-type]
    ):
        assert asyncio.run(check.evaluate(data())) == Approved()


def test_two_methods_with_one_name_keep_the_worse_whatever_the_order() -> None:
    worse = '2,9,7,1,2,"a@1-2@m.py","m.py","a","a()",1,2'
    milder = '2,3,7,1,2,"a@3-4@m.py","m.py","a","a()",3,4'

    assert parse_functions([worse, milder]) == {("m.py", "a"): 9}
    assert parse_functions([milder, worse]) == {("m.py", "a"): 9}


def test_a_function_of_complexity_zero_is_kept_as_zero() -> None:
    assert parse_functions(['2,0,7,1,2,"a@1-2@m.py","m.py","a","a()",1,2']) == {("m.py", "a"): 0}


def test_the_ratchet_adds_up_rows_that_name_the_same_file_and_rule() -> None:
    drafts = (
        EvidenceDraft("lint.F401", Target(kind=TargetKind.FILE, id="a.py"), 2, "violations"),
        EvidenceDraft("lint.F401", Target(kind=TargetKind.FILE, id="a.py"), 3, "violations"),
        EvidenceDraft("lint.E501", Target(kind=TargetKind.FILE, id="a.py"), 1, "violations"),
    )

    assert violations(drafts) == {("a.py", "F401"): 5, ("a.py", "E501"): 1}


# -- measuring -------------------------------------------------------------------------------------


def test_an_undecided_measurement_carries_its_result_and_says_what_it_is() -> None:
    result = NotApplicable(missing_capability="x")

    stop = Undecided(result)

    assert stop.result is result and str(stop) == "not_applicable"


def test_an_operation_the_adapter_does_not_offer_is_not_applicable_by_name(
    log: EventLog, tmp_path: Path
) -> None:
    with pytest.raises(Undecided) as stop:
        asyncio.run(
            measure(
                tools(log, tmp_path),
                PythonAdapter(),
                Operation.MUTATION,
                "mutation",
                OperationRequest(root=tmp_path),
            )
        )

    assert stop.value.result == NotApplicable(missing_capability="mutation")


def test_output_nobody_can_read_makes_the_check_inconclusive_with_the_run_to_blame(
    log: EventLog, tmp_path: Path
) -> None:
    adapter = PythonAdapter(python=(sys.executable, "-c", "raise SystemExit(3)"))
    plan = adapter.plan(Operation.TEST, OperationRequest(root=tmp_path))
    assert isinstance(plan, CommandPlan)

    with pytest.raises(Undecided) as stop:
        asyncio.run(measure_plan(tools(log, tmp_path), adapter, Operation.TEST, "tests", plan))

    assert stop.value.result == Inconclusive(
        reason=InconclusiveReason.TOOL_FAILED,
        detail="tests: pytest ended with 3",
        tool_run_ids=("run_tool:t1-a1:tests:1",),
    )


@pytest.mark.parametrize(
    ("check", "operation", "name"),
    [
        (TestsCheck, "test", "tests"),
        (FormatCheck, "format", "format"),
        (LintCheck, "lint", "lint"),
    ],
)
def test_a_command_of_the_repository_replaces_the_adapters_in_every_check(
    log: EventLog, tmp_path: Path, check: type, operation: str, name: str
) -> None:
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    adapter = PythonAdapter()
    changes = Changes((Change(ChangeKind.MODIFIED, "a.py"),), 1, ())
    values = {"commands": {operation: [sys.executable, "-c", "raise SystemExit(3)"]}}
    arguments = {
        TestsCheck: (tools(log, tmp_path), adapter, tmp_path),
        FormatCheck: (tools(log, tmp_path), adapter, tmp_path, changes),
        LintCheck: (tools(log, tmp_path), adapter, tmp_path, changes, {}),
    }[check]

    result = asyncio.run(check(*arguments).evaluate(data(values)))

    assert isinstance(result, Inconclusive)
    assert result.detail.startswith(name + ": ")


def test_a_build_that_failed_without_naming_a_file_is_the_build_that_failed(
    log: EventLog, tmp_path: Path
) -> None:
    values = {"commands": {"build": [sys.executable, "-c", "raise SystemExit(1)"]}}
    check = BuildCheck(tools(log, tmp_path), PythonAdapter(), tmp_path)

    result = asyncio.run(check.evaluate(data(values)))

    assert isinstance(result, Rejected)
    assert [f.describe() for f in result.findings] == ["the build failed [build]"]


def test_no_test_at_all_is_a_failure_when_the_base_had_some_and_fine_when_it_had_none(
    log: EventLog, tmp_path: Path
) -> None:
    values = {"commands": {"test": [sys.executable, "-c", "raise SystemExit(5)"]}}
    adapter = PythonAdapter()

    none_before = TestsCheck(tools(log, tmp_path), adapter, tmp_path)
    some_before = TestsCheck(
        tools(log, tmp_path), adapter, tmp_path, passing=frozenset({"tests/a.py::t"})
    )

    assert asyncio.run(none_before.evaluate(data(values))) == Approved()
    result = asyncio.run(some_before.evaluate(data(values)))
    assert isinstance(result, Rejected)
    assert [f.describe() for f in result.findings] == [
        "a test that passed on the base is missing or did not pass [tests/a.py::t]"
    ]


def test_a_run_that_was_stopped_says_it_was_stopped(tmp_path: Path) -> None:
    plan = CommandPlan((str(Path(sys.executable)),), tmp_path)
    result = ProcessResult(Outcome.CANCELLED, None, 0.0, tmp_path / "x.log")

    inconclusive = Execution("lint", plan, "run_tool:t:lint:1", result).inconclusive("lint")

    assert inconclusive.reason is InconclusiveReason.TOOL_FAILED
    assert inconclusive.detail == f"lint: {Path(sys.executable).name} was stopped"
    assert inconclusive.tool_run_ids == ("run_tool:t:lint:1",)


# -- scope -----------------------------------------------------------------------------------------


def test_a_directory_entry_may_end_in_the_letter_x() -> None:
    assert in_scope("projX/a.py", ("projX/",)) is True
    assert in_scope("proj/a.py", ("projX/",)) is False


def evaluate_scope(changes: Changes, declared: tuple[str, ...] = ()) -> Rejected:
    task = TaskInfo("t1", "t1-s", "intent", ("src",), 8, 400)
    check = ScopeCheck(changes, task, lambda path: PythonAdapter().classify(path) or None, declared)  # type: ignore[arg-type,return-value]
    result = asyncio.run(check.evaluate(data()))
    assert isinstance(result, Rejected)
    return result


def test_a_silencing_comment_in_a_patch_without_a_file_is_a_problem_of_the_diff() -> None:
    patch = ("@@ -0,0 +1 @@", "+x = 1  # noqa")
    changes = Changes((Change(ChangeKind.MODIFIED, "src/a.py"),), 1, patch)

    result = evaluate_scope(changes)

    assert [(f.message, f.target) for f in result.findings] == [
        ("a comment that silences a tool was added", "diff")
    ]


def test_several_declared_and_changed_files_are_listed_with_commas() -> None:
    changes = Changes(
        (Change(ChangeKind.MODIFIED, "src/a.py"), Change(ChangeKind.MODIFIED, "src/b.py")), 2, ()
    )

    result = evaluate_scope(changes, declared=("src/x.py", "src/y.py"))

    assert result.findings[0].message == (
        "the declared files differ from the changed ones "
        "(declared but not changed: src/x.py, src/y.py; "
        "changed but not declared: src/a.py, src/b.py)"
    )


# -- the scanner -----------------------------------------------------------------------------------


def secrets_check(log: EventLog, tmp_path: Path, report: str | None) -> SecretsCheck:
    script = "raise SystemExit(2)"
    if report is not None:
        script = (
            "import sys\n"
            "path = sys.argv[sys.argv.index('--report-path') + 1]\n"
            f"open(path, 'w').write({report!r})\n"
            "raise SystemExit(2)\n"
        )
    patch = ("+++ b/a.py", "@@ -0,0 +1,2 @@", "+one", "+two")
    changes = Changes((Change(ChangeKind.ADDED, "a.py"),), 2, patch)
    return SecretsCheck(
        tools(log, tmp_path),
        tmp_path,
        changes,
        tmp_path / "reports",
        (sys.executable, "-c", script, "--"),
    )


def secrets_findings(check: SecretsCheck) -> list[str]:
    result = asyncio.run(check.evaluate(data()))
    assert isinstance(result, Rejected)
    return [f.describe() for f in result.findings]


@pytest.mark.parametrize("report", [None, "not json", "{}", '{"a": 1}', "[]", '"text"'])
def test_a_report_without_leaks_in_it_gives_one_unplaced_finding(
    log: EventLog, tmp_path: Path, report: str | None
) -> None:
    assert secrets_findings(secrets_check(log, tmp_path, report)) == [UNPLACED.describe()]
    assert UNPLACED.target == "diff" and UNPLACED.message == "a possible secret was added"


def test_a_leak_without_a_rule_is_an_unknown_rule_and_one_that_is_not_an_object_too(
    log: EventLog, tmp_path: Path
) -> None:
    report = json.dumps([{"StartLine": 2}, "text", {"RuleID": "r", "StartLine": 1}])

    assert secrets_findings(secrets_check(log, tmp_path, report)) == [
        "a possible secret was added (rule unknown) [a.py at a.py:2]",
        "a possible secret was added (rule unknown) [diff]",
        "a possible secret was added (rule r) [a.py at a.py:1]",
    ]


@pytest.mark.parametrize("line", [0, 3, -1, "1", None])
def test_a_line_the_scanner_names_outside_the_added_ones_is_not_placed(
    log: EventLog, tmp_path: Path, line: object
) -> None:
    report = json.dumps([{"RuleID": "r", "StartLine": line}])

    assert secrets_findings(secrets_check(log, tmp_path, report)) == [
        "a possible secret was added (rule r) [diff]"
    ]
