"""A run interrupted at any boundary resumes and ends where an uninterrupted run ends.

Contracts 2 and 4 together, now with the real orchestrator: the log is the only memory, and the
idempotency table says what to do with the operation that was in flight.
"""

import os
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from forja.core.events import EventLog, LogUnusable
from forja.core.process import creation_token
from forja.core.states import ExecutionState
from tests.orchestrator.crash import (
    PAUSE_ENV,
    STALL_ENV,
    STALLED_MARKER,
    TORN_ENV,
    Counting,
    CrashAfter,
    Interrupted,
)
from tests.orchestrator.fakes import ContentMeasurer, ScriptedAgent
from tests.orchestrator.harness import RUN, World
from tests.orchestrator.resume_support import (
    agent_was_running,
    fingerprint,
    scenario,
    with_one_more_discarded_attempt,
    without_discarded_in_summary,
)

PROJECT = Path(__file__).resolve().parents[2]
# Lines the uninterrupted scenario writes, and the cuts made in it: after every event that is not
# a progress line, and a torn line before every intent and effect. A test fails if they drift.
TOTAL_LINES = 66
CUTS = (
    0, 2, 4, 5, 6, 7, 8, 9, 10, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26,
    27, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 47, 48, 49, 50, 51, 52, 53,
    54, 55, 56, 57, 58, 59, 60, 61, 63, 64, 65,
)  # fmt: skip
TORN_CUTS = (
    3, 4, 5, 6, 7, 8, 15, 16, 20, 21, 22, 23, 26, 29, 31, 32, 34, 35, 37, 38, 39, 40, 43, 46, 48,
    49, 51, 52, 55, 56, 57, 58, 62, 63,
)  # fmt: skip

pytestmark = pytest.mark.slow


@pytest.fixture
def world(tmp_path: Path, template: Path) -> World:
    return World.create(tmp_path / "world", template)


@pytest.fixture(scope="session")
def reference(tmp_path_factory: pytest.TempPathFactory, template: Path) -> dict[str, Any]:
    """An uninterrupted run: its facts, and the line each event landed on."""
    world = World.create(tmp_path_factory.mktemp("reference") / "world", template)
    counter = Counting()
    marks: list[tuple[int, str]] = []
    log = world.open(write=counter)
    log.subscribe(lambda e: marks.append((counter.count, e.type)))
    outcome, log = scenario(world, log=log)
    assert outcome.state is ExecutionState.DELIVERED
    return {"fingerprint": fingerprint(world, log), "lines": counter.count, "marks": marks}


def restart(world: World, **log_options: Any) -> Any:
    """What a new process does: open the log (recovering a torn line) and run."""
    return scenario(
        world,
        log=world.open(**log_options),
        agent=ScriptedAgent(in_process=False, by_feedback=True),
        measurer=ContentMeasurer(),
    )


def test_an_uninterrupted_run_has_the_shape_the_cuts_were_made_for(
    reference: dict[str, Any],
) -> None:
    fp = reference["fingerprint"]

    assert (fp["execution"], fp["task"], fp["stage"]) == ("delivered", "integrated", "committed")
    assert fp["attempts"] == {"rejected": 1, "committed": 1}
    assert fp["open_operations"] == [] and fp["infra_failures"] == 0
    assert fp["worktrees"] == 1
    assert reference["lines"] == TOTAL_LINES
    boundaries = {n for n, kind in reference["marks"] if kind != "progress"}
    assert (boundaries | {0}) - {1} == set(CUTS)  # line 1 is a run not yet confirmed
    assert {n - 1 for n, kind in reference["marks"] if kind in ("intent", "effect")} == set(
        TORN_CUTS
    )


CASES = [(cut, False) for cut in CUTS] + [(cut, True) for cut in TORN_CUTS]


@pytest.mark.parametrize(
    ("cut", "torn"), CASES, ids=[f"{cut}-{'torn' if torn else 'clean'}" for cut, torn in CASES]
)
def test_interrupted_after_the_nth_line_the_run_resumes_to_the_same_end(
    world: World, reference: dict[str, Any], cut: int, torn: bool
) -> None:
    try:
        scenario(world, log=world.open(write=CrashAfter(cut, torn=torn)))
    except (Interrupted, LogUnusable):
        pass  # the runner may report the dead log instead of the failed write itself
    else:
        raise AssertionError("the run ended before the cut")
    running = agent_was_running(world)

    outcome, log = restart(world)

    assert outcome.state is ExecutionState.DELIVERED
    expected = reference["fingerprint"]
    reached = fingerprint(world, log)
    if running:
        expected = with_one_more_discarded_attempt(expected)
        reached = without_discarded_in_summary(reached)
    assert reached == expected


# -- deaths that a raised exception cannot imitate ------------------------------------------------


def _stalled(world: World) -> bool:
    return (world.root / STALLED_MARKER).exists()


def _agent_started(world: World) -> bool:
    log = world.run_dir / "events.jsonl"
    return log.exists() and b"process_started" in log.read_bytes()


KILLS: dict[str, tuple[dict[str, str], Callable[[World], bool]]] = {
    "agent running": ({PAUSE_ENV: "60"}, _agent_started),
    "commit made, effect not recorded": ({STALL_ENV: "commit_stage:before_effect"}, _stalled),
    "commit not yet made": ({STALL_ENV: "commit_stage:after_intent"}, _stalled),
    "event line half written": ({TORN_ENV: "40"}, _stalled),
}


def _start_driver(world: World, extra: dict[str, str]) -> subprocess.Popen[bytes]:
    return subprocess.Popen(
        [sys.executable, "-m", "tests.orchestrator.driver", str(world.root)],
        cwd=PROJECT,
        env={**os.environ, **extra},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )


def _kill_when(
    world: World, driver: subprocess.Popen[bytes], ready: Callable[[World], bool]
) -> None:
    try:
        deadline = time.monotonic() + 90
        while not ready(world):
            assert driver.poll() is None, driver.stderr.read().decode() if driver.stderr else ""
            assert time.monotonic() < deadline, "the driver never reached the point"
            time.sleep(0.05)
    finally:
        driver.kill()
        driver.wait()
        if driver.stderr:
            driver.stderr.close()


@pytest.mark.parametrize("name", list(KILLS))
def test_a_process_killed_for_real_leaves_a_run_that_resumes_to_the_same_end(
    world: World, reference: dict[str, Any], name: str
) -> None:
    extra, ready = KILLS[name]
    _kill_when(world, _start_driver(world, extra), ready)
    running = agent_was_running(world)

    outcome, log = restart(world)

    assert outcome.state is ExecutionState.DELIVERED
    expected = reference["fingerprint"]
    reached = fingerprint(world, log)
    if running:
        expected = with_one_more_discarded_attempt(expected)
        reached = without_discarded_in_summary(reached)
    assert reached == expected


def test_the_agent_of_a_killed_run_is_not_left_running(world: World) -> None:
    _kill_when(world, _start_driver(world, {PAUSE_ENV: "60"}), _agent_started)
    with EventLog.open(world.run_dir / "events.jsonl", RUN) as log:
        (identity,) = log.state.leftover_processes()

    restart(world)

    assert creation_token(identity.pid) != identity.creation_token


@pytest.mark.parametrize("resume_lines", [0, 1, 2, 3])
def test_a_resume_interrupted_in_the_middle_can_be_resumed_again(
    world: World, reference: dict[str, Any], resume_lines: int
) -> None:
    with pytest.raises((Interrupted, LogUnusable)):
        scenario(world, log=world.open(write=CrashAfter(_after_agent_call_started(reference))))

    with pytest.raises((Interrupted, LogUnusable)):
        restart(world, write=CrashAfter(resume_lines))
    outcome, log = restart(world)

    assert outcome.state is ExecutionState.DELIVERED
    assert without_discarded_in_summary(fingerprint(world, log)) == (
        with_one_more_discarded_attempt(reference["fingerprint"])
    )


def _after_agent_call_started(reference: dict[str, Any]) -> int:
    """The line count right after the first ``process_started`` of the scenario."""
    marks = reference["marks"]
    intents = [i for i, (_, kind) in enumerate(marks) if kind == "intent"]
    call = next(i for i in intents if marks[i + 1][1] == "progress")
    return int(marks[call + 1][0])
