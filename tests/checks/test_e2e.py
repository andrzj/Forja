"""Gate 6: the E2E run, judged with a script that passes, fails or knocks on the network."""

import asyncio
import os
import sys
from collections.abc import Mapping
from pathlib import Path

import pytest

from forja.checks.e2e import E2ECheck
from forja.checks.tooling import Tools
from forja.core.adapters import (
    CommandPlan,
    EvidenceDraft,
    NotSupported,
    Operation,
    OperationRequest,
    Parsed,
    ParseResult,
    ToolOutput,
)
from forja.core.events import EventLog
from forja.core.evidence import Target, TargetKind
from forja.core.gates import (
    Approved,
    GateInput,
    GateResult,
    Inconclusive,
    NotApplicable,
    Rejected,
)
from forja.core.states import ExecutionState, Level
from tests.checks.support import RUN, sinks
from tests.core.adapters.fakes import FakeLanguageAdapter
from tests.core.events.support import FakeClock

SCRIPT = Path(__file__).with_name("fake_e2e.py")
FLOW = "flow"


class Scripted(FakeLanguageAdapter):
    """Plans a harmless process and reads its exit code: 0 passed, 1 failed, 3 reported nothing."""

    def __init__(self, language: str = "python") -> None:
        self.language = language

    def plan(self, operation: Operation, request: OperationRequest) -> CommandPlan | NotSupported:
        return CommandPlan((sys.executable, "-c", "pass"), request.root)

    def parse(self, operation: Operation, output: ToolOutput) -> ParseResult:
        outcome = {0: "passed", 1: "failed"}.get(output.exit_code or 0)
        if outcome is None:
            return Parsed(())
        draft = EvidenceDraft("test.outcome", Target(kind=TargetKind.SYMBOL, id=FLOW), outcome, "x")
        return Parsed((draft,))


@pytest.fixture
def log(tmp_path: Path) -> EventLog:
    opened = EventLog.open(tmp_path / "events.jsonl", RUN, clock=FakeClock())
    opened.append_transition(Level.EXECUTION, RUN, None, ExecutionState.PREPARING)
    return opened


def judge(
    log: EventLog,
    tmp_path: Path,
    mode: str | None,
    *adapters: Scripted,
    declared: Mapping[str, tuple[str, ...]] | None = None,
    quarantine: frozenset[str] = frozenset(),
    passing: frozenset[str] = frozenset(),
) -> GateResult:
    tools = Tools(
        sinks=sinks,
        log=log,
        level=Level.EXECUTION,
        target=RUN,
        logs=tmp_path / "logs",
        host_env=dict(os.environ),
    )
    command = {"python": (sys.executable, str(SCRIPT), mode)} if mode is not None else {}
    check = E2ECheck(
        tools,
        adapters or (Scripted(),),
        tmp_path,
        declared or command,
        {},
        quarantine=quarantine,
        passing=passing,
    )
    data = GateInput(tmp_path, "head", "t1", "t1-s", "t1-a1")
    return asyncio.run(check.evaluate(data))


def test_without_a_declared_command_the_gate_does_not_run(log: EventLog, tmp_path: Path) -> None:
    assert judge(log, tmp_path, None) == NotApplicable(missing_capability="e2e_command")


def test_a_passing_run_that_stays_in_loopback_is_approved(log: EventLog, tmp_path: Path) -> None:
    assert isinstance(judge(log, tmp_path, "pass"), Approved)


def test_a_failing_test_rejects(log: EventLog, tmp_path: Path) -> None:
    result = judge(log, tmp_path, "fail")
    assert isinstance(result, Rejected)
    assert [(f.message, f.target) for f in result.findings] == [("e2e test failed", FLOW)]


def test_a_try_at_the_network_rejects_even_when_the_tests_pass(
    log: EventLog, tmp_path: Path
) -> None:
    result = judge(log, tmp_path, "net-pass")
    assert isinstance(result, Rejected)
    assert [(f.message, f.target) for f in result.findings] == [
        ("tried to reach the network", "blocked.test:80")
    ]


def test_a_failure_and_a_try_at_the_network_are_both_reported(
    log: EventLog, tmp_path: Path
) -> None:
    result = judge(log, tmp_path, "net-fail")
    assert isinstance(result, Rejected)
    assert {f.target for f in result.findings} == {FLOW, "blocked.test:80"}


def test_a_test_the_base_showed_unstable_does_not_reject(log: EventLog, tmp_path: Path) -> None:
    assert isinstance(judge(log, tmp_path, "fail", quarantine=frozenset({FLOW})), Approved)


def test_a_test_that_passed_on_the_base_and_vanished_rejects(log: EventLog, tmp_path: Path) -> None:
    result = judge(log, tmp_path, "gone", passing=frozenset({FLOW}))
    assert isinstance(result, Rejected)
    assert result.findings[0].target == FLOW


def test_a_command_that_does_not_start_is_inconclusive(log: EventLog, tmp_path: Path) -> None:
    declared = {"python": ("no-such-program-for-forja",)}
    assert isinstance(judge(log, tmp_path, None, declared=declared), Inconclusive)


def test_a_language_without_a_command_is_left_out(log: EventLog, tmp_path: Path) -> None:
    result = judge(log, tmp_path, "pass", Scripted("python"), Scripted("go"))
    assert isinstance(result, Approved)


def test_a_rejection_wins_over_a_language_whose_run_could_not_be_made(
    log: EventLog, tmp_path: Path
) -> None:
    declared = {
        "python": (sys.executable, str(SCRIPT), "net-pass"),
        "go": ("no-such-program-for-forja",),
    }
    result = judge(log, tmp_path, None, Scripted("python"), Scripted("go"), declared=declared)
    assert isinstance(result, Rejected)


def test_the_gate_inconclusive_when_nothing_else_was_seen_to_fail_in_another_language(
    log: EventLog, tmp_path: Path
) -> None:
    declared = {
        "python": (sys.executable, str(SCRIPT), "pass"),
        "go": ("no-such-program-for-forja",),
    }
    result = judge(log, tmp_path, None, Scripted("python"), Scripted("go"), declared=declared)
    assert isinstance(result, Inconclusive)


def test_a_passing_test_that_now_fails_is_reported_once(log: EventLog, tmp_path: Path) -> None:
    result = judge(log, tmp_path, "fail", passing=frozenset({FLOW}))
    assert isinstance(result, Rejected)
    assert [(f.message, f.target) for f in result.findings] == [("e2e test failed", FLOW)]


class Unsupported(Scripted):
    def plan(self, operation: Operation, request: OperationRequest) -> CommandPlan | NotSupported:
        return NotSupported("test", "no tests here")


def test_a_language_whose_adapter_cannot_run_tests_is_left_out(
    log: EventLog, tmp_path: Path
) -> None:
    declared = {"python": (sys.executable, str(SCRIPT), "pass")}
    result = judge(log, tmp_path, None, Unsupported(), declared=declared)
    assert result == NotApplicable(missing_capability="e2e_command")


def test_a_trap_that_cannot_open_is_inconclusive(
    log: EventLog, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def refuse(self: object) -> None:
        raise OSError("no sockets")

    monkeypatch.setattr("forja.checks.e2e.NetworkTrap.__aenter__", refuse)
    assert isinstance(judge(log, tmp_path, "pass"), Inconclusive)
