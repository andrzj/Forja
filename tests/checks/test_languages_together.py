"""Build, tests and the per-language checks over a project with more than one language."""

import asyncio
from pathlib import Path

import pytest

from forja.checks.build_and_tests import BuildCheck, TestsCheck
from forja.checks.each import EachLanguage, Part
from forja.checks.tooling import Tools
from forja.core.events import EventLog
from forja.core.gates import (
    Approved,
    Finding,
    GateInput,
    GateResult,
    Inconclusive,
    InconclusiveReason,
    NotApplicable,
    Rejected,
)
from forja.core.states import ExecutionState, Level
from tests.checks.support import RUN, Stub, draft, sinks
from tests.core.events.support import FakeClock


def data() -> GateInput:
    return GateInput(Path("."), "c" * 40, "t1", "t1-s", "t1-a1")


@pytest.fixture
def tools(tmp_path: Path) -> Tools:
    log = EventLog.open(tmp_path / "events.jsonl", RUN, clock=FakeClock())
    log.append_transition(Level.EXECUTION, RUN, None, ExecutionState.PREPARING)
    return Tools(
        sinks=sinks,
        log=log,
        level=Level.ATTEMPT,
        target="t1-a1",
        logs=tmp_path / "logs",
        host_env={},
    )


def test_the_build_of_every_language_counts(tools: Tools, tmp_path: Path) -> None:
    py = Stub("python", ".py", tmp_path)
    go = Stub("go", ".go", tmp_path, after=(draft("build.failed", "go.mod"),))

    result = asyncio.run(BuildCheck(tools, (py, go), tmp_path).evaluate(data()))

    assert isinstance(result, Rejected)
    assert [f.target for f in result.findings] == ["go.mod"]
    assert len(py.requests) == len(go.requests) == 1


def test_the_tests_of_every_language_run_and_a_failure_in_one_rejects(
    tools: Tools, tmp_path: Path
) -> None:
    py = Stub("python", ".py", tmp_path, after=(draft("test.outcome", "t/a.py::ok", "passed"),))
    go = Stub("go", ".go", tmp_path, after=(draft("test.outcome", "pkg.TestB", "failed"),))

    result = asyncio.run(TestsCheck(tools, (py, go), tmp_path).evaluate(data()))

    assert isinstance(result, Rejected)
    assert [f.target for f in result.findings] == ["pkg.TestB"]


def test_a_test_that_passed_on_the_base_is_missing_only_if_no_language_ran_it(
    tools: Tools, tmp_path: Path
) -> None:
    py = Stub("python", ".py", tmp_path, after=(draft("test.outcome", "t/a.py::ok", "passed"),))
    go = Stub("go", ".go", tmp_path, after=(draft("test.outcome", "pkg.TestB", "passed"),))
    base = frozenset({"t/a.py::ok", "pkg.TestB"})

    assert (
        asyncio.run(TestsCheck(tools, (py, go), tmp_path, passing=base).evaluate(data()))
        == Approved()
    )
    gone = asyncio.run(TestsCheck(tools, (py,), tmp_path, passing=base).evaluate(data()))
    assert isinstance(gone, Rejected)
    assert [f.target for f in gone.findings] == ["pkg.TestB"]


class Fixed:
    """A check that always answers the same."""

    def __init__(self, result: GateResult, requires: frozenset[str] = frozenset()) -> None:
        self.id, self.gate, self.requires, self.result = "mutation", 7, requires, result
        self.ran = False

    async def evaluate(self, data: GateInput) -> GateResult:
        self.ran = True
        return self.result


def each(*parts: Part) -> EachLanguage:
    return EachLanguage(parts, "mutation", 7)


def rejected_for(target: str) -> Rejected:
    return Rejected(findings=(Finding(message="no", target=target),))


def test_one_language_rejecting_rejects_all_and_the_findings_add_up() -> None:
    caps = frozenset({"coverage"})
    result = asyncio.run(
        each(
            Part(Fixed(rejected_for("a.py")), caps),
            Part(Fixed(Approved()), caps),
            Part(Fixed(rejected_for("b.go")), caps),
        ).evaluate(data())
    )

    assert isinstance(result, Rejected)
    assert [f.target for f in result.findings] == ["a.py", "b.go"]


def test_a_language_nobody_could_measure_is_not_a_pass() -> None:
    stuck = Inconclusive(reason=InconclusiveReason.TOOL_FAILED, detail="mutation: no")
    caps: frozenset[str] = frozenset()

    result = asyncio.run(
        each(Part(Fixed(Approved()), caps), Part(Fixed(stuck), caps)).evaluate(data())
    )

    assert result == stuck


def test_a_language_without_the_capability_is_not_applicable_and_never_runs() -> None:
    needs = Fixed(Approved(), frozenset({"coverage"}))
    runs = Fixed(Approved(), frozenset({"coverage"}))

    only_one = asyncio.run(
        each(Part(needs, frozenset()), Part(runs, frozenset({"coverage"}))).evaluate(data())
    )
    none = asyncio.run(
        each(Part(Fixed(Approved(), frozenset({"coverage"})), frozenset())).evaluate(data())
    )

    assert only_one == Approved() and not needs.ran and runs.ran
    assert none == NotApplicable(missing_capability="coverage")
