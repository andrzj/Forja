"""The SAST ratchet: only findings the attempt added reprove, judged with a stand-in for semgrep."""

import asyncio
import sys
from pathlib import Path

import pytest

from forja.checks.changes import Change, ChangeKind, Changes
from forja.checks.sast import SastCheck
from forja.checks.tooling import Tools
from forja.core.events import EventLog
from forja.core.gates import (
    Approved,
    GateInput,
    GateResult,
    Inconclusive,
    InconclusiveReason,
    NotApplicable,
)
from forja.core.gates.models import Rejected
from forja.core.states import ExecutionState, Level
from tests.checks.fake_semgrep import RULES
from tests.checks.support import RUN, sinks
from tests.core.events.support import FakeClock


@pytest.fixture
def log(tmp_path: Path) -> EventLog:
    opened = EventLog.open(tmp_path / "events.jsonl", RUN, clock=FakeClock())
    opened.append_transition(Level.EXECUTION, RUN, None, ExecutionState.PREPARING)
    return opened


def tools(log: EventLog, tmp_path: Path) -> Tools:
    return Tools(
        sinks=sinks,
        log=log,
        level=Level.EXECUTION,
        target=RUN,
        logs=tmp_path / "logs",
        host_env={},
    )


FAKE_SEMGREP = Path(__file__).with_name("fake_semgrep.py")
BAD = "FAKE-FINDING"
OTHER = "FAKE-OTHER"


def judge(
    log: EventLog,
    tmp_path: Path,
    changes: tuple[Change, ...],
    before: dict[str, str],
    *,
    rules: str | None = "rules",
    semgrep: tuple[str, ...] | None = None,
) -> GateResult:
    worktree = tmp_path / "work"
    config = None
    if rules is not None:
        config = tmp_path / "rules.yml"
        config.write_text(rules, encoding="utf-8")
    check = SastCheck(
        tools(log, tmp_path),
        worktree,
        Changes(changes, 0, ()),
        before,
        tmp_path / "reports",
        config,
        semgrep or (sys.executable, str(FAKE_SEMGREP)),
    )
    data = GateInput(worktree, "c" * 40, "t1", "t1-s", "t1-a1")
    return asyncio.run(check.evaluate(data))


def write(tmp_path: Path, name: str, text: str) -> None:
    path = tmp_path / "work" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def modified(path: str) -> Change:
    return Change(ChangeKind.MODIFIED, path)


def test_the_stand_in_knows_the_rules_these_tests_use() -> None:
    assert RULES[BAD] == "fake-rule" and RULES[OTHER] == "other-rule"


def test_without_rules_the_check_does_not_run(log: EventLog, tmp_path: Path) -> None:
    write(tmp_path, "a.py", BAD)

    result = judge(log, tmp_path, (modified("a.py"),), {"a.py": "x\n"}, rules=None)

    assert result == NotApplicable(missing_capability="semgrep_config")
    assert not (tmp_path / "reports").exists()


def test_nothing_changed_means_nothing_to_scan(log: EventLog, tmp_path: Path) -> None:
    result = judge(log, tmp_path, (), {}, semgrep=("no-such-semgrep-anywhere",))

    assert result == Approved()


def test_a_deleted_file_is_not_scanned(log: EventLog, tmp_path: Path) -> None:
    result = judge(
        log, tmp_path, (Change(ChangeKind.DELETED, "a.py"),), {}, semgrep=("no-such-semgrep",)
    )

    assert result == Approved()


def test_a_clean_file_approves(log: EventLog, tmp_path: Path) -> None:
    write(tmp_path, "a.py", "x = 1\n")

    assert judge(log, tmp_path, (modified("a.py"),), {"a.py": "x = 0\n"}) == Approved()


def test_a_new_finding_rejects_with_rule_file_and_counts(log: EventLog, tmp_path: Path) -> None:
    write(tmp_path, "a.py", f"{BAD}\n{BAD}\n")

    result = judge(log, tmp_path, (modified("a.py"),), {"a.py": f"{BAD}\n"})

    assert isinstance(result, Rejected)
    (finding,) = result.findings
    assert finding.message == "1 new fake-rule finding(s)"
    assert (finding.target, finding.measured, finding.limit) == ("a.py", 2, 1)


def test_an_old_finding_that_stays_does_not_reprove(log: EventLog, tmp_path: Path) -> None:
    write(tmp_path, "a.py", f"x = 1\n{BAD}\n")

    assert judge(log, tmp_path, (modified("a.py"),), {"a.py": f"{BAD}\n"}) == Approved()


def test_a_finding_of_another_rule_is_new(log: EventLog, tmp_path: Path) -> None:
    write(tmp_path, "a.py", f"{BAD}\n{OTHER}\n")

    result = judge(log, tmp_path, (modified("a.py"),), {"a.py": f"{BAD}\n"})

    assert isinstance(result, Rejected)
    assert [f.message for f in result.findings] == ["1 new other-rule finding(s)"]


def test_a_finding_in_a_new_file_is_new(log: EventLog, tmp_path: Path) -> None:
    write(tmp_path, "b.py", BAD)

    result = judge(log, tmp_path, (Change(ChangeKind.ADDED, "b.py"),), {})

    assert isinstance(result, Rejected)
    assert [f.target for f in result.findings] == ["b.py"]


def test_a_renamed_file_keeps_the_findings_it_had(log: EventLog, tmp_path: Path) -> None:
    write(tmp_path, "new.py", BAD)
    renamed = Change(ChangeKind.RENAMED, "new.py", "old.py")

    assert judge(log, tmp_path, (renamed,), {"old.py": BAD}) == Approved()


def test_the_old_text_is_scanned_next_to_the_current_files(log: EventLog, tmp_path: Path) -> None:
    write(tmp_path, "a.py", "x = 1\n")
    write(tmp_path, "keep.py", BAD)  # not changed, so not scanned in either state

    assert judge(log, tmp_path, (modified("a.py"),), {"a.py": "x = 0\n"}) == Approved()
    assert (tmp_path / "work" / "a.py").read_text(encoding="utf-8") == "x = 1\n"


def test_a_file_named_like_an_option_is_still_a_file(log: EventLog, tmp_path: Path) -> None:
    write(tmp_path, "-x.py", BAD)

    result = judge(log, tmp_path, (Change(ChangeKind.ADDED, "-x.py"),), {})

    assert isinstance(result, Rejected)
    assert [f.target for f in result.findings] == ["-x.py"]


def test_semgrep_failing_is_inconclusive_never_a_pass(log: EventLog, tmp_path: Path) -> None:
    write(tmp_path, "a.py", BAD)

    result = judge(log, tmp_path, (modified("a.py"),), {}, rules="fail:7")

    assert isinstance(result, Inconclusive)
    assert result.reason is InconclusiveReason.TOOL_FAILED
    assert result.detail == "sast: semgrep ended with 7"
    assert result.tool_run_ids == (f"run_tool:{RUN}:sast:1",)


def test_semgrep_that_runs_on_the_new_files_but_not_the_old_is_inconclusive(
    log: EventLog, tmp_path: Path
) -> None:
    write(tmp_path, "a.py", "x = 1\n")
    script = (
        "import json, sys\n"
        "out = [a for a in sys.argv if a.startswith('--json-output=')][0].split('=', 1)[1]\n"
        "bad = 'forja-sast-before' in __import__('os').getcwd()\n"
        "json.dump({'results': []}, open(out, 'w'))\n"
        "raise SystemExit(3 if bad else 0)\n"
    )

    result = judge(
        log,
        tmp_path,
        (modified("a.py"),),
        {"a.py": "x = 0\n"},
        semgrep=(sys.executable, "-c", script),
    )

    assert isinstance(result, Inconclusive)
    assert result.detail == "sast_before: semgrep ended with 3"


@pytest.mark.parametrize("report", ["not json", "{}", '{"results": [1]}', '{"results": [{}]}'])
def test_a_report_that_cannot_be_read_is_inconclusive(
    log: EventLog, tmp_path: Path, report: str
) -> None:
    write(tmp_path, "a.py", "x = 1\n")
    script = (
        "import sys\n"
        "out = [a for a in sys.argv if a.startswith('--json-output=')][0].split('=', 1)[1]\n"
        f"open(out, 'w').write({report!r})\n"
    )

    result = judge(log, tmp_path, (modified("a.py"),), {}, semgrep=(sys.executable, "-c", script))

    assert isinstance(result, Inconclusive)
    assert result.detail == "sast: the semgrep report cannot be read"


def test_a_stale_report_is_not_read(log: EventLog, tmp_path: Path) -> None:
    write(tmp_path, "a.py", "x = 1\n")
    (tmp_path / "reports").mkdir()
    (tmp_path / "reports" / "sast.json").write_text('{"results": []}')

    result = judge(log, tmp_path, (modified("a.py"),), {}, semgrep=(sys.executable, "-c", "pass"))

    assert isinstance(result, Inconclusive)
    assert result.detail == "sast: the semgrep report cannot be read"


def test_a_semgrep_that_cannot_start_is_inconclusive(log: EventLog, tmp_path: Path) -> None:
    write(tmp_path, "a.py", "x = 1\n")

    result = judge(log, tmp_path, (modified("a.py"),), {}, semgrep=("no-such-semgrep-anywhere",))

    assert isinstance(result, Inconclusive)
    assert result.detail == "sast: no-such-semgrep-anywhere could not start"


def test_windows_paths_in_the_report_are_read_as_posix(tmp_path: Path) -> None:
    from forja.checks.sast import _count  # noqa: PLC0415

    report = tmp_path / "r.json"
    report.write_text('{"results": [{"check_id": "r", "path": ".\\\\src\\\\a.py"}]}')

    assert _count(report, tmp_path / "rules") == {("src/a.py", "r"): 1}


def test_the_rule_is_named_without_the_path_semgrep_puts_before_it(tmp_path: Path) -> None:
    from forja.checks.sast import _count  # noqa: PLC0415

    report = tmp_path / "r.json"
    report.write_text(
        '{"results": [{"check_id": "C.Users.me.runs.r1.semgrep-rules.shell-true", "path": "a.py"}]}'
    )

    assert _count(report, tmp_path / "semgrep-rules") == {("a.py", "shell-true"): 1}
