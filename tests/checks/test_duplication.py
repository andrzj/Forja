"""The duplication ratchet: only clones the attempt added reprove, judged with a stand-in jscpd."""

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import JsonValue

from forja.checks.duplication import DuplicationCheck, _finding
from forja.checks.duplication_report import Clone, CloneSide
from forja.checks.tooling import Tools
from forja.core.events import EventLog
from forja.core.gates import Approved, GateInput, GateResult, Inconclusive, InconclusiveReason
from forja.core.gates.models import Rejected
from forja.core.states import ExecutionState, Level
from tests.checks.fake_jscpd import MARKER
from tests.checks.support import RUN, sinks
from tests.core.events.support import FakeClock

FAKE_JSCPD = Path(__file__).with_name("fake_jscpd.py")
CLONE = f"{MARKER}\n"


@pytest.fixture
def log(tmp_path: Path) -> EventLog:
    opened = EventLog.open(tmp_path / "events.jsonl", RUN, clock=FakeClock())
    opened.append_transition(Level.EXECUTION, RUN, None, ExecutionState.PREPARING)
    return opened


@pytest.fixture
def work(tmp_path: Path) -> Path:
    root = tmp_path / "work"
    root.mkdir()
    git(root, "init", "-q")
    return root


def git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=root, check=True
    )


def commit(root: Path, **files: str) -> None:
    """The parent commit: what the files held before the attempt."""
    for name, text in files.items():
        (root / name).write_text(text, encoding="utf-8", newline="\n")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "base")


def attempt(root: Path, **files: str) -> None:
    for name, text in files.items():
        (root / name).write_text(text, encoding="utf-8", newline="\n")


def judge(
    log: EventLog,
    tmp_path: Path,
    production: tuple[str, ...],
    *,
    jscpd: tuple[str, ...] | None = None,
    ignore: tuple[str, ...] = (),
    min_tokens: int = 50,
    min_lines: int = 5,
    base: str = "HEAD",
    values: dict[str, JsonValue] | None = None,
) -> GateResult:
    tools = Tools(
        sinks=sinks,
        log=log,
        level=Level.EXECUTION,
        target=RUN,
        logs=tmp_path / "logs",
        host_env=dict(os.environ),  # the stand-in runs git, as jscpd does
    )
    check = DuplicationCheck(
        tools,
        tmp_path / "work",
        production,
        tmp_path / "reports",
        jscpd or (sys.executable, str(FAKE_JSCPD)),
        min_tokens,
        min_lines,
        ignore,
        base,
    )
    data = GateInput(tmp_path / "work", "c" * 40, "t1", "t1-s", "t1-a1", values=values or {})
    return asyncio.run(check.evaluate(data))


def test_nothing_changed_means_nothing_to_scan(log: EventLog, tmp_path: Path) -> None:
    result = judge(log, tmp_path, (), jscpd=("no-such-jscpd-anywhere",))

    assert result == Approved()
    assert not (tmp_path / "reports").exists()


def test_a_new_clone_in_a_changed_file_rejects_with_where_and_how_much(
    log: EventLog, tmp_path: Path, work: Path
) -> None:
    commit(work, **{"a.py": "x = 1\n", "b.py": CLONE})
    attempt(work, **{"a.py": f"x = 1\n{CLONE}"})

    result = judge(log, tmp_path, ("a.py",))

    assert isinstance(result, Rejected)
    (finding,) = result.findings
    assert finding.target == "a.py"
    assert finding.location is not None
    assert (finding.location.path, finding.location.line) == ("a.py", 2)
    assert finding.message == "6 duplicated lines, also in b.py:1"
    assert (finding.measured, finding.limit) == (6, 0)


def test_an_old_clone_that_stays_does_not_reprove(
    log: EventLog, tmp_path: Path, work: Path
) -> None:
    commit(work, **{"a.py": CLONE, "b.py": CLONE})
    attempt(work, **{"a.py": f"x = 1\n{CLONE}"})

    assert judge(log, tmp_path, ("a.py",)) == Approved()


def test_a_new_clone_between_files_the_attempt_did_not_change_does_not_reprove(
    log: EventLog, tmp_path: Path, work: Path
) -> None:
    commit(work, **{"a.py": "x = 1\n", "b.py": "y = 1\n", "c.py": "z = 1\n"})
    attempt(work, **{"b.py": CLONE, "c.py": CLONE})

    assert judge(log, tmp_path, ("a.py",)) == Approved()


def test_a_clone_between_two_changed_files_reproves_both(
    log: EventLog, tmp_path: Path, work: Path
) -> None:
    commit(work, **{"a.py": "x = 1\n", "b.py": "y = 1\n"})
    attempt(work, **{"a.py": CLONE, "b.py": CLONE})

    result = judge(log, tmp_path, ("a.py", "b.py"))

    assert isinstance(result, Rejected)
    assert [(f.target, f.message) for f in result.findings] == [
        ("a.py", "6 duplicated lines, also in b.py:1"),
        ("b.py", "6 duplicated lines, also in a.py:1"),
    ]


def test_jscpd_is_given_the_parent_commit_the_thresholds_and_the_ignored_paths(
    log: EventLog, tmp_path: Path, work: Path
) -> None:
    commit(work, **{"a.py": "x = 1\n"})

    judge(log, tmp_path, ("a.py",), ignore=("tests/**",), min_tokens=70, min_lines=8)

    call = json.loads((tmp_path / "reports" / "argv.json").read_text(encoding="utf-8"))
    args = call["args"]
    assert args[args.index("--baseline-from-ref") + 1] == "HEAD"
    assert args[args.index("-r") + 1] == "json"
    assert args[args.index("-o") + 1] == str(tmp_path / "reports")
    assert args[-1] == "."
    assert call["config"] == {"minTokens": 70, "minLines": 8, "ignore": ["tests/**"]}


def _config(tmp_path: Path) -> dict[str, int]:
    call = json.loads((tmp_path / "reports" / "argv.json").read_text(encoding="utf-8"))
    return {key: call["config"][key] for key in ("minTokens", "minLines")}


def test_the_limits_of_the_policy_replace_the_thresholds(
    log: EventLog, tmp_path: Path, work: Path
) -> None:
    commit(work, **{"a.py": "x = 1\n"})

    judge(log, tmp_path, ("a.py",), values={"limits": {"min_tokens": 90, "min_lines": 9}})

    assert _config(tmp_path) == {"minTokens": 90, "minLines": 9}


@pytest.mark.parametrize("limits", [{}, {"min_tokens": True, "min_lines": "9"}, "none"])
def test_a_limit_that_is_missing_or_not_an_integer_leaves_the_threshold(
    log: EventLog, tmp_path: Path, work: Path, limits: JsonValue
) -> None:
    commit(work, **{"a.py": "x = 1\n"})

    judge(log, tmp_path, ("a.py",), min_tokens=70, min_lines=8, values={"limits": limits})

    assert _config(tmp_path) == {"minTokens": 70, "minLines": 8}


def test_an_ignored_path_is_not_scanned(log: EventLog, tmp_path: Path, work: Path) -> None:
    (work / "tests").mkdir()
    commit(work, **{"a.py": "x = 1\n"})
    attempt(work, **{"a.py": CLONE, "tests/test_a.py": CLONE})

    assert judge(log, tmp_path, ("a.py",), ignore=("tests/*",)) == Approved()
    assert isinstance(judge(log, tmp_path, ("a.py",)), Rejected)


def test_jscpd_that_ends_badly_is_inconclusive(log: EventLog, tmp_path: Path, work: Path) -> None:
    commit(work, **{"a.py": "x = 1\n", "jscpd-fail": "7"})

    result = judge(log, tmp_path, ("a.py",))

    assert isinstance(result, Inconclusive)
    assert result.reason is InconclusiveReason.TOOL_FAILED
    assert result.detail == "duplication: jscpd ended with 7"
    assert result.tool_run_ids == (f"run_tool:{RUN}:duplication:1",)


@pytest.mark.parametrize("marker", ["jscpd-garbage", "jscpd-silent"])
def test_a_report_that_cannot_be_read_is_inconclusive(
    log: EventLog, tmp_path: Path, work: Path, marker: str
) -> None:
    commit(work, **{"a.py": "x = 1\n", marker: ""})

    result = judge(log, tmp_path, ("a.py",))

    assert isinstance(result, Inconclusive)
    assert result.detail == "duplication: the jscpd report cannot be read"


def test_a_stale_report_is_not_read(log: EventLog, tmp_path: Path, work: Path) -> None:
    commit(work, **{"a.py": "x = 1\n", "jscpd-silent": ""})
    (tmp_path / "reports").mkdir()
    (tmp_path / "reports" / "jscpd-report.json").write_text('{"duplicates": []}', encoding="utf-8")

    result = judge(log, tmp_path, ("a.py",))

    assert isinstance(result, Inconclusive)


def test_a_jscpd_that_cannot_start_is_inconclusive(
    log: EventLog, tmp_path: Path, work: Path
) -> None:
    commit(work, **{"a.py": "x = 1\n"})

    result = judge(log, tmp_path, ("a.py",), jscpd=("no-such-jscpd-anywhere",))

    assert isinstance(result, Inconclusive)
    assert result.detail == "duplication: no-such-jscpd-anywhere could not start"


def test_the_clone_is_new_against_the_base_it_is_given(
    log: EventLog, tmp_path: Path, work: Path
) -> None:
    commit(work, **{"a.py": "x = 1\n", "b.py": CLONE})
    git(work, "tag", "base")
    commit(work, **{"a.py": CLONE})  # the implementer's committed code

    assert judge(log, tmp_path, ("a.py",)) == Approved()
    assert isinstance(judge(log, tmp_path, ("a.py",), base="base"), Rejected)


def test_a_clone_side_that_starts_at_line_zero_is_located_at_line_one() -> None:
    side = CloneSide("a.py", 0, 5)
    other = CloneSide("b.py", 3, 8)

    finding = _finding(Clone(side, other, 6, 60, True, "exact", "python"), side, other)

    assert finding.location is not None
    assert finding.location.line == 1
