"""Gate 10 against the real tools and registries.

Skipped unless the tool is there: ``semgrep`` and ``osv-scanner`` on the PATH, or the paths in
``FORJA_SEMGREP`` and ``FORJA_OSV_SCANNER``. The vulnerability and license lookups and the
registries need the network, so those tests also need ``FORJA_LIVE=1``.
"""

import asyncio
import os
import shutil
from pathlib import Path

import pytest

from forja.checks.changes import Change, ChangeKind, Changes
from forja.checks.dependency_audit import DependencyAuditCheck
from forja.checks.registries import Missing, look_up, urllib_get
from forja.checks.sast import SastCheck
from forja.checks.tooling import Tools
from forja.core.events import EventLog
from forja.core.gates import Approved, GateInput, GateResult, Inconclusive
from forja.core.gates.models import Rejected
from forja.core.states import ExecutionState, Level
from tests.checks.support import RUN, sinks
from tests.core.events.support import FakeClock

SEMGREP = os.environ.get("FORJA_SEMGREP") or shutil.which("semgrep")
OSV = os.environ.get("FORJA_OSV_SCANNER") or shutil.which("osv-scanner")
LIVE = pytest.mark.skipif(
    not os.environ.get("FORJA_LIVE"), reason="needs the network: FORJA_LIVE=1"
)
# Sample text for semgrep to read, never run: the rule is about a call to eval in the code it scans
RULES = (
    "rules:\n  - id: no-eval\n    pattern: eval(...)\n    message: no eval\n"
    "    languages: [python]\n    severity: WARNING\n"
)


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
        host_env=dict(os.environ),
        timeouts={"sast": 120.0, "sast_before": 120.0},
    )


def evaluate(check: SastCheck | DependencyAuditCheck, tmp_path: Path) -> GateResult:
    return asyncio.run(check.evaluate(GateInput(tmp_path / "work", "c" * 40, "t", "s", "a")))


def work(tmp_path: Path, name: str, text: str) -> None:
    (tmp_path / "work" / name).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / "work" / name).write_text(text, encoding="utf-8", newline="\n")


def sast(log: EventLog, tmp_path: Path, rules: str, now: str, was: str) -> GateResult:
    config = tmp_path / "rules"
    config.mkdir(parents=True, exist_ok=True)
    if rules:
        (config / "r.yml").write_text(rules, encoding="utf-8")
    work(tmp_path, "a.py", now)
    check = SastCheck(
        tools(log, tmp_path),
        tmp_path / "work",
        Changes((Change(ChangeKind.MODIFIED, "a.py"),), 0, ()),
        {"a.py": was},
        tmp_path / "reports",
        config,
        (SEMGREP or "semgrep",),
    )
    return evaluate(check, tmp_path)


@pytest.mark.skipif(SEMGREP is None, reason="semgrep is not installed")
class TestSemgrep:
    def test_a_new_finding_rejects_and_an_old_one_does_not(
        self, log: EventLog, tmp_path: Path
    ) -> None:
        added = sast(log, tmp_path, RULES, 'eval("1")\neval("2")\n', 'eval("1")\n')

        assert isinstance(added, Rejected)
        assert (
            added.findings[0].message.startswith("1 new ")
            and "no-eval" in added.findings[0].message
        )
        assert (added.findings[0].measured, added.findings[0].limit) == (2, 1)
        assert sast(log, tmp_path / "again", RULES, 'eval("1")\n', 'eval("1")\n') == Approved()

    def test_a_clean_change_approves(self, log: EventLog, tmp_path: Path) -> None:
        assert sast(log, tmp_path, RULES, "x = 1\n", "x = 0\n") == Approved()

    def test_a_directory_without_rules_is_inconclusive_with_the_code_semgrep_gives(
        self, log: EventLog, tmp_path: Path
    ) -> None:
        result = sast(log, tmp_path, "", 'eval("1")\n', "x = 0\n")

        assert isinstance(result, Inconclusive)
        assert result.detail == "sast: semgrep ended with 7"


def audit(
    log: EventLog, tmp_path: Path, now: str, was: str, forbidden: frozenset[str] = frozenset()
) -> GateResult:
    work(tmp_path, "requirements.txt", now)
    check = DependencyAuditCheck(
        tools(log, tmp_path),
        tmp_path / "work",
        Changes((Change(ChangeKind.MODIFIED, "requirements.txt"),), 0, ()),
        {"requirements.txt": was},
        tmp_path / "reports",
        forbidden,
        (OSV or "osv-scanner",),
    )
    return evaluate(check, tmp_path)


@LIVE
@pytest.mark.skipif(OSV is None, reason="osv-scanner is not installed")
class TestOsvScanner:
    def test_a_package_with_known_vulnerabilities_added_to_a_lockfile_rejects(
        self, log: EventLog, tmp_path: Path
    ) -> None:
        result = audit(log, tmp_path, "requests==2.33.1\ndjango==1.11.0\n", "requests==2.33.1\n")

        assert isinstance(result, Rejected)
        assert all("in django 1.11.0" in f.message for f in result.findings)
        assert result.findings[0].target == "requirements.txt"

    def test_what_was_already_there_does_not_reprove(self, log: EventLog, tmp_path: Path) -> None:
        text = "django==1.11.0\n"

        assert audit(log, tmp_path, text, text) == Approved()

    def test_a_forbidden_license_is_found_even_in_a_package_without_vulnerabilities(
        self, log: EventLog, tmp_path: Path
    ) -> None:
        result = audit(
            log, tmp_path, "requests==2.33.1\n", "idna==3.11\n", frozenset({"apache-2.0"})
        )

        assert isinstance(result, Rejected)
        # osv-scanner also resolves what requests needs, so other findings may come with it
        assert "forbidden license Apache-2.0 in requests 2.33.1" in [
            f.message for f in result.findings
        ]

    def test_the_scan_counts_a_package_once_for_each_lockfile_that_has_it(
        self, log: EventLog, tmp_path: Path
    ) -> None:
        """Seen with osv-scanner 2.7.0: two lockfiles with the same package give a count of 2 in
        ``license_summary``, as many as the report lists, so the accounting stays even."""
        for name in ("one/requirements.txt", "two/requirements.txt"):
            work(tmp_path, name, "certifi==2026.1.4\n")
        changes = Changes(
            tuple(
                Change(ChangeKind.ADDED, n)
                for n in ("one/requirements.txt", "two/requirements.txt")
            ),
            0,
            (),
        )
        check = DependencyAuditCheck(
            tools(log, tmp_path),
            tmp_path / "work",
            changes,
            {},
            tmp_path / "reports",
            frozenset({"mpl-2.0"}),
            (OSV or "osv-scanner",),
        )

        result = evaluate(check, tmp_path)

        assert isinstance(result, Rejected)
        assert any(f.message.startswith("forbidden license MPL-2.0") for f in result.findings)

    def test_a_file_with_no_package_is_nothing_to_audit(
        self, log: EventLog, tmp_path: Path
    ) -> None:
        assert audit(log, tmp_path, "\n", "\n") == Approved()


@LIVE
class TestRegistries:
    @pytest.mark.parametrize(
        ("ecosystem", "name", "dated", "counted"),
        [
            ("npm", "left-pad", True, True),
            ("npm", "@types/node", True, True),
            ("PyPI", "requests", True, False),
            ("PyPI", "Zope.Interface", True, False),
            ("Go", "github.com/BurntSushi/toml", False, False),
            ("Maven", "com.google.inject:guice", True, False),
            ("NuGet", "Newtonsoft.Json", True, True),
        ],
    )
    def test_a_package_that_exists_is_found(
        self, ecosystem: str, name: str, dated: bool, counted: bool
    ) -> None:
        standing = asyncio.run(look_up(ecosystem, name, urllib_get))

        assert (standing.first_published is not None) is dated
        assert (standing.downloads is not None) is counted

    @pytest.mark.parametrize(
        ("ecosystem", "name"),
        [
            ("npm", "zzzz-forja-ghost-9187263"),
            ("PyPI", "zzzz-forja-ghost-9187263"),
            ("Go", "github.com/zzzz-forja/ghost-9187263"),
            ("Maven", "com.zzzz-forja:ghost-9187263"),
            ("NuGet", "Zzzz.Forja.Ghost.9187263"),
        ],
    )
    def test_a_package_that_does_not_exist_is_missing(self, ecosystem: str, name: str) -> None:
        with pytest.raises(Missing):
            asyncio.run(look_up(ecosystem, name, urllib_get))
