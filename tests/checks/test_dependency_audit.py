"""The dependency audit: only what the attempt added reproves (a stand-in for osv-scanner)."""

import asyncio
import sys
from pathlib import Path

import pytest

from forja.checks.changes import Change, ChangeKind, Changes
from forja.checks.dependency_audit import DependencyAuditCheck, is_artifact
from forja.checks.tooling import Tools
from forja.core.events import EventLog
from forja.core.gates import Approved, GateInput, GateResult, Inconclusive, InconclusiveReason
from forja.core.gates.models import Rejected
from forja.core.states import ExecutionState, Level
from tests.checks.support import RUN, sinks
from tests.core.events.support import FakeClock

FAKE_OSV = Path(__file__).with_name("fake_osv_scanner.py")
LOCK = "requirements.txt"


@pytest.fixture
def log(tmp_path: Path) -> EventLog:
    opened = EventLog.open(tmp_path / "events.jsonl", RUN, clock=FakeClock())
    opened.append_transition(Level.EXECUTION, RUN, None, ExecutionState.PREPARING)
    return opened


def judge(
    log: EventLog,
    tmp_path: Path,
    changes: tuple[Change, ...],
    before: dict[str, str],
    *,
    forbidden: frozenset[str] = frozenset(),
    osv: tuple[str, ...] | None = None,
) -> GateResult:
    tools = Tools(
        sinks=sinks,
        log=log,
        level=Level.EXECUTION,
        target=RUN,
        logs=tmp_path / "logs",
        host_env={},
    )
    check = DependencyAuditCheck(
        tools,
        tmp_path / "work",
        Changes(changes, 0, ()),
        before,
        tmp_path / "reports",
        forbidden,
        osv or (sys.executable, str(FAKE_OSV)),
    )
    data = GateInput(tmp_path / "work", "c" * 40, "t1", "t1-s", "t1-a1")
    return asyncio.run(check.evaluate(data))


def write(tmp_path: Path, name: str, text: str) -> None:
    path = tmp_path / "work" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def modified(path: str = LOCK) -> tuple[Change, ...]:
    return (Change(ChangeKind.MODIFIED, path),)


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("requirements.txt", True),
        ("svc/requirements.txt", True),
        ("web\\package-lock.json", True),
        ("go.mod", True),
        ("pom.xml", True),
        ("package.json", False),
        ("src/requirements.py", False),
        ("go.sum", False),
    ],
)
def test_only_what_osv_scanner_reads_is_audited(path: str, expected: bool) -> None:
    assert is_artifact(path) is expected


def test_without_a_dependency_file_changed_nothing_runs(log: EventLog, tmp_path: Path) -> None:
    result = judge(log, tmp_path, modified("a.py"), {}, osv=("no-such-osv-scanner",))

    assert result == Approved()
    assert not (tmp_path / "reports").exists()


def test_a_deleted_dependency_file_is_not_audited(log: EventLog, tmp_path: Path) -> None:
    deleted = (Change(ChangeKind.DELETED, LOCK),)

    assert judge(log, tmp_path, deleted, {LOCK: "a 1\n"}, osv=("no-such",)) == Approved()


def test_a_clean_change_approves(log: EventLog, tmp_path: Path) -> None:
    write(tmp_path, LOCK, "a 1\nb 2\n")

    assert judge(log, tmp_path, modified(), {LOCK: "a 1\n"}) == Approved()


def test_a_new_vulnerability_rejects_naming_advisory_package_and_file(
    log: EventLog, tmp_path: Path
) -> None:
    write(tmp_path, LOCK, "a 1\nb 2 vulns=GHSA-1\n")

    result = judge(log, tmp_path, modified(), {LOCK: "a 1\n"})

    assert isinstance(result, Rejected)
    (finding,) = result.findings
    assert finding.message == "new vulnerability GHSA-1 in b 2"
    assert finding.target == LOCK


def test_an_old_vulnerability_that_stays_does_not_reprove(log: EventLog, tmp_path: Path) -> None:
    write(tmp_path, LOCK, "a 1 vulns=GHSA-1\nb 2\n")

    assert judge(log, tmp_path, modified(), {LOCK: "a 1 vulns=GHSA-1\n"}) == Approved()


def test_a_new_advisory_on_the_same_package_is_new(log: EventLog, tmp_path: Path) -> None:
    write(tmp_path, LOCK, "a 1 vulns=GHSA-1,GHSA-2\n")

    result = judge(log, tmp_path, modified(), {LOCK: "a 1 vulns=GHSA-1\n"})

    assert isinstance(result, Rejected)
    assert [f.message for f in result.findings] == ["new vulnerability GHSA-2 in a 1"]


def test_a_version_bump_that_keeps_the_vulnerability_is_a_new_pair(
    log: EventLog, tmp_path: Path
) -> None:
    write(tmp_path, LOCK, "a 2 vulns=GHSA-1\n")

    result = judge(log, tmp_path, modified(), {LOCK: "a 1 vulns=GHSA-1\n"})

    assert isinstance(result, Rejected)


def test_a_new_dependency_file_has_nothing_to_compare_with(log: EventLog, tmp_path: Path) -> None:
    write(tmp_path, LOCK, "a 1 vulns=GHSA-1\n")
    added = (Change(ChangeKind.ADDED, LOCK),)

    assert isinstance(judge(log, tmp_path, added, {}), Rejected)


def test_a_file_with_no_package_is_nothing_to_audit(log: EventLog, tmp_path: Path) -> None:
    write(tmp_path, LOCK, "\n")

    assert judge(log, tmp_path, modified(), {LOCK: "\n"}) == Approved()


def test_a_forbidden_license_rejects_only_when_the_list_is_given(
    log: EventLog, tmp_path: Path
) -> None:
    write(tmp_path, LOCK, "a 1 licenses=GPL-3.0\n")

    assert judge(log, tmp_path, modified(), {LOCK: "b 1\n"}) == Approved()
    result = judge(log, tmp_path, modified(), {LOCK: "b 1\n"}, forbidden=frozenset({"gpl-3.0"}))

    assert isinstance(result, Rejected)
    assert [f.message for f in result.findings] == ["forbidden license GPL-3.0 in a 1"]


@pytest.mark.parametrize(
    "expression", ["(MIT OR GPL-3.0)", "MIT AND GPL-3.0", "GPL-3.0 WITH Classpath-exception-2.0"]
)
def test_a_forbidden_id_inside_an_expression_counts(
    log: EventLog, tmp_path: Path, expression: str
) -> None:
    write(tmp_path, LOCK, f"a 1 licenses={expression.replace(' ', '_')}\n")
    result = judge(log, tmp_path, modified(), {LOCK: "b 1\n"}, forbidden=frozenset({"gpl-3.0"}))

    assert isinstance(result, Rejected)


@pytest.mark.parametrize("placeholder", ["UNKNOWN", "non-standard", "NOASSERTION"])
def test_a_placeholder_is_not_a_known_license(
    log: EventLog, tmp_path: Path, placeholder: str
) -> None:
    write(tmp_path, LOCK, f"a 1 licenses={placeholder}\n")

    result = judge(log, tmp_path, modified(), {LOCK: "b 1\n"}, forbidden=frozenset({"gpl-3.0"}))

    assert isinstance(result, Inconclusive)


def test_an_old_forbidden_license_does_not_reprove(log: EventLog, tmp_path: Path) -> None:
    write(tmp_path, LOCK, "a 1 licenses=GPL-3.0\nb 1 licenses=MIT\n")
    old = {LOCK: "a 1 licenses=GPL-3.0\n"}

    assert judge(log, tmp_path, modified(), old, forbidden=frozenset({"gpl-3.0"})) == Approved()


def test_a_package_without_a_license_is_inconclusive_when_licenses_are_audited(
    log: EventLog, tmp_path: Path
) -> None:
    write(tmp_path, LOCK, "a 1\n")

    result = judge(log, tmp_path, modified(), {LOCK: "b 1\n"}, forbidden=frozenset({"gpl-3.0"}))

    assert isinstance(result, Inconclusive)
    assert result.detail == "dependency_audit: the license of a 1 is unknown"
    assert judge(log, tmp_path, modified(), {LOCK: "b 1\n"}) == Approved()


def test_a_vulnerability_wins_over_an_unknown_license(log: EventLog, tmp_path: Path) -> None:
    write(tmp_path, LOCK, "a 1\nc 1 vulns=X\n")

    result = judge(log, tmp_path, modified(), {LOCK: "b 1\n"}, forbidden=frozenset({"gpl-3.0"}))

    assert isinstance(result, Rejected)


def test_a_scanner_failing_is_inconclusive_never_a_pass(log: EventLog, tmp_path: Path) -> None:
    write(tmp_path, LOCK, "fail:129")

    result = judge(log, tmp_path, modified(), {LOCK: "a 1\n"})

    assert isinstance(result, Inconclusive)
    assert result.reason is InconclusiveReason.TOOL_FAILED
    assert result.detail == "dependency_audit: osv-scanner ended with 129"
    assert result.tool_run_ids == (f"run_tool:{RUN}:dependency_audit:1",)


def test_a_scanner_that_runs_on_the_new_files_but_not_the_old_is_inconclusive(
    log: EventLog, tmp_path: Path
) -> None:
    write(tmp_path, LOCK, "a 1\n")

    result = judge(log, tmp_path, modified(), {LOCK: "fail:127"})

    assert isinstance(result, Inconclusive)
    assert result.detail == "dependency_audit_before: osv-scanner ended with 127"


@pytest.mark.parametrize("report", ["not json", "[]", '{"results": [1]}', '{"results": [{}]}'])
def test_a_report_that_cannot_be_read_is_inconclusive(
    log: EventLog, tmp_path: Path, report: str
) -> None:
    write(tmp_path, LOCK, "a 1\n")
    script = (
        "import sys\n"
        "out = sys.argv[sys.argv.index('--output-file') + 1]\n"
        f"open(out, 'w').write({report!r})\n"
    )

    result = judge(log, tmp_path, modified(), {}, osv=(sys.executable, "-c", script))

    assert isinstance(result, Inconclusive)
    assert result.detail == "dependency_audit: the osv-scanner report cannot be read"


def test_a_scanner_that_cannot_start_is_inconclusive(log: EventLog, tmp_path: Path) -> None:
    write(tmp_path, LOCK, "a 1\n")

    result = judge(log, tmp_path, modified(), {}, osv=("no-such-osv-scanner-anywhere",))

    assert isinstance(result, Inconclusive)
    assert result.detail == "dependency_audit: no-such-osv-scanner-anywhere could not start"


def test_a_file_named_like_an_option_is_still_a_file(log: EventLog, tmp_path: Path) -> None:
    write(tmp_path, "-x/go.mod", "a 1 vulns=X\n")
    added = (Change(ChangeKind.ADDED, "-x/go.mod"),)

    result = judge(log, tmp_path, added, {})

    assert isinstance(result, Rejected)
    assert [f.target for f in result.findings] == ["-x/go.mod"]
