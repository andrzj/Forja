"""Deaths a raised exception cannot imitate, and a resume that is itself interrupted."""

import os
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from forja.core.events import EventLog, LogUnusable
from forja.core.idempotency import Decision
from forja.core.process import creation_token
from tests.e2e.driver import (
    PAUSE_ENV,
    STALL_ENV,
    STALLED_MARKER,
    TORN_ENV,
    CrashAfter,
    Interrupted,
)
from tests.e2e.support import assert_same_end, open_operations, restart, run_until_it_ends
from tests.e2e.world import World, expected_after_discarding_one_attempt, fingerprint

PROJECT = Path(__file__).resolve().parents[2]
WAIT_SECONDS = 60

pytestmark = pytest.mark.slow


def _stalled(world: World) -> bool:
    return (world.root / STALLED_MARKER).exists()


def _agent_started(world: World) -> bool:
    return world.events.exists() and b"process_started" in world.events.read_bytes()


# name -> (environment for the driver, what to wait for before killing it)
KILLS: dict[str, tuple[dict[str, str], Callable[[World], bool]]] = {
    "agent running": ({PAUSE_ENV: "60"}, _agent_started),
    "commit made, effect not recorded": ({STALL_ENV: "commit_stage:before_effect"}, _stalled),
    "commit not yet made": ({STALL_ENV: "commit_stage:after_intent"}, _stalled),
    "event line half written": ({TORN_ENV: "30"}, _stalled),
}


@pytest.mark.parametrize("name", list(KILLS))
def test_a_process_killed_for_real_leaves_a_run_that_resumes_to_the_same_end(
    world: World, reference: dict[str, Any], name: str
) -> None:
    extra, ready = KILLS[name]
    driver = subprocess.Popen(
        [sys.executable, "-m", "tests.e2e.driver", str(world.root)],
        cwd=PROJECT,
        env={**os.environ, **extra},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    try:
        deadline = time.monotonic() + WAIT_SECONDS
        while not ready(world):
            assert driver.poll() is None, driver.stderr.read().decode() if driver.stderr else ""
            assert time.monotonic() < deadline, f"never reached: {name}"
            time.sleep(0.05)
    finally:
        driver.kill()
        driver.wait()
        if driver.stderr:
            driver.stderr.close()
    open_at_crash = open_operations(world)

    plan = restart(world)

    assert_same_end(world, reference["fingerprint"], plan, open_at_crash)


def test_the_agent_killed_for_real_is_not_left_running(world: World) -> None:
    driver = subprocess.Popen(
        [sys.executable, "-m", "tests.e2e.driver", str(world.root)],
        cwd=PROJECT,
        env={**os.environ, PAUSE_ENV: "60"},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + WAIT_SECONDS
        while not _agent_started(world):
            assert time.monotonic() < deadline
            time.sleep(0.05)
    finally:
        driver.kill()
        driver.wait()
    probe = world.root / "probe.jsonl"
    probe.write_bytes(world.events.read_bytes())
    with EventLog.open(probe, "run1") as log:
        (identity,) = log.state.leftover_processes()

    restart(world)

    assert creation_token(identity.pid) != identity.creation_token  # that process is gone


@pytest.mark.parametrize("lines_resume_gets", [0, 1, 2])
def test_a_resume_interrupted_in_the_middle_can_be_resumed_again(
    world: World, reference: dict[str, Any], lines_resume_gets: int
) -> None:
    after_agent_started = next(
        n
        for n, kind, label in reference["marks"]
        if kind == "progress" and "call_agent_cli" in label
    )
    with pytest.raises((Interrupted, LogUnusable)):
        run_until_it_ends(world, write=CrashAfter(after_agent_started))

    with pytest.raises((Interrupted, LogUnusable)):
        restart(world, write=CrashAfter(lines_resume_gets))
    plan = restart(world)

    assert fingerprint(world) == expected_after_discarding_one_attempt(reference["fingerprint"])
    assert all(a.reconciliation.decision is not Decision.REDO for a in plan.actions)
