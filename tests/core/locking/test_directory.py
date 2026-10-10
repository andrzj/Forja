import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from forja.core.locking import (
    DirectoryLockSettings,
    LockHeld,
    LockOwner,
    release,
    try_acquire,
)
from forja.core.locking.directory import OWNER_FILE
from forja.core.process import creation_token
from tests.core.locking.support import NO_SLEEP, age, dead_owner, write_lock
from tests.core.process.support import minimal_env


def owner(run_id: str = "run1") -> LockOwner:
    return LockOwner.current(run_id)


def test_taking_a_free_lock_records_who_holds_it(tmp_path: Path) -> None:
    mine = owner()

    result = try_acquire(tmp_path / "run.lock", mine, NO_SLEEP)

    recorded = json.loads((tmp_path / "run.lock" / OWNER_FILE).read_bytes())
    assert result.taken_over is None
    assert recorded["pid"] == os.getpid()
    assert recorded["creation_token"] == creation_token(os.getpid())
    assert recorded["run_id"] == "run1" and recorded["nonce"] == mine.nonce
    assert recorded["machine"] == mine.machine


def test_a_live_holder_is_never_pushed_aside(tmp_path: Path) -> None:
    first = owner("first")
    try_acquire(tmp_path / "run.lock", first, NO_SLEEP)

    with pytest.raises(LockHeld) as info:
        try_acquire(tmp_path / "run.lock", owner("second"), NO_SLEEP)

    assert info.value.owner == first
    assert "running process" in info.value.reason


def test_release_gives_the_lock_back_once_and_only_to_its_owner(tmp_path: Path) -> None:
    directory = tmp_path / "run.lock"
    mine, other = owner(), owner("other")
    try_acquire(directory, mine, NO_SLEEP)

    assert release(directory, other) is False  # not the holder
    assert directory.exists()
    assert release(directory, mine) is True
    assert not directory.exists()
    assert release(directory, mine) is False
    assert [p.name for p in tmp_path.iterdir()] == []

    assert try_acquire(directory, other, NO_SLEEP).owner == other


def test_an_abandoned_lock_is_taken_over_and_the_previous_owner_is_reported(
    tmp_path: Path,
) -> None:
    directory = tmp_path / "run.lock"
    gone = dead_owner()
    write_lock(directory, gone)
    mine = owner()

    result = try_acquire(directory, mine, NO_SLEEP)

    assert result.taken_over is not None
    assert result.taken_over.previous == gone
    assert "gone" in result.taken_over.reason
    assert json.loads((directory / OWNER_FILE).read_bytes())["nonce"] == mine.nonce
    assert [p.name for p in tmp_path.iterdir()] == ["run.lock"]  # no stale or guard leftovers


def test_a_reused_pid_does_not_keep_a_dead_owners_lock_alive(tmp_path: Path) -> None:
    directory = tmp_path / "run.lock"
    token = creation_token(os.getpid())
    assert token is not None
    write_lock(directory, dead_owner(pid=os.getpid(), creation_token=token + 1))

    assert try_acquire(directory, owner(), NO_SLEEP).taken_over is not None


def test_a_live_pid_with_an_unknown_start_time_is_treated_as_alive(tmp_path: Path) -> None:
    directory = tmp_path / "run.lock"
    write_lock(directory, dead_owner(pid=os.getpid(), creation_token=None))

    with pytest.raises(LockHeld):
        try_acquire(directory, owner(), NO_SLEEP)


def test_a_lock_from_another_machine_cannot_be_judged_so_it_is_respected(tmp_path: Path) -> None:
    directory = tmp_path / "run.lock"
    write_lock(directory, dead_owner(machine="some-other-host"))

    with pytest.raises(LockHeld, match="another machine"):
        try_acquire(directory, owner(), NO_SLEEP)
    assert directory.exists()


def test_a_lock_still_being_acquired_is_left_alone_until_the_grace_runs_out(
    tmp_path: Path,
) -> None:
    directory = tmp_path / "run.lock"
    directory.mkdir()  # the other process created it but has not written its record yet

    with pytest.raises(LockHeld, match="being acquired"):
        try_acquire(directory, owner(), NO_SLEEP)

    age(directory, 100)
    result = try_acquire(directory, owner(), NO_SLEEP)
    assert result.taken_over is not None and result.taken_over.previous is None


@pytest.mark.parametrize("content", [b"not json", b"[]", b'{"pid": 1}', b'{"surprise": true}'])
def test_an_unreadable_owner_record_counts_as_no_owner(tmp_path: Path, content: bytes) -> None:
    directory = tmp_path / "run.lock"
    directory.mkdir()
    (directory / OWNER_FILE).write_bytes(content)

    with pytest.raises(LockHeld, match="being acquired"):
        try_acquire(directory, owner(), NO_SLEEP)
    age(directory, 100)
    assert try_acquire(directory, owner(), NO_SLEEP).taken_over is not None


def test_the_grace_period_follows_the_injected_clock(tmp_path: Path) -> None:
    directory = tmp_path / "run.lock"
    directory.mkdir()
    later = DirectoryLockSettings(sleep=lambda s: None, now=lambda: time.time() + 6)

    assert try_acquire(directory, owner(), later).taken_over is not None


def test_a_takeover_guard_left_by_a_crash_is_cleaned_up(tmp_path: Path) -> None:
    directory = tmp_path / "run.lock"
    write_lock(directory, dead_owner())
    guard = tmp_path / "run.lock.takeover"
    guard.mkdir()
    age(guard, 120)

    assert try_acquire(directory, owner(), NO_SLEEP).taken_over is not None
    assert not guard.exists()


def test_a_fresh_guard_means_someone_else_is_taking_over_so_we_give_way(tmp_path: Path) -> None:
    directory = tmp_path / "run.lock"
    write_lock(directory, dead_owner())
    (tmp_path / "run.lock.takeover").mkdir()

    with pytest.raises(LockHeld, match="settle a race"):
        try_acquire(directory, owner(), NO_SLEEP)


def test_a_crash_while_writing_the_record_leaves_no_lock_behind(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import forja.core.locking.directory as module

    def boom(path: Path, data: bytes) -> None:
        raise OSError("disk gone")

    monkeypatch.setattr(module, "atomic_write_bytes", boom)
    with pytest.raises(OSError, match="disk gone"):
        try_acquire(tmp_path / "run.lock", owner(), NO_SLEEP)
    monkeypatch.undo()

    assert not (tmp_path / "run.lock").exists()
    assert try_acquire(tmp_path / "run.lock", owner(), NO_SLEEP).taken_over is None


HOLDER = """
import os, sys, time
from pathlib import Path
from forja.core.locking import LockOwner, try_acquire
try_acquire(Path(sys.argv[1]), LockOwner.current("child-run"))
print("holding", os.getpid(), flush=True)
time.sleep(60)
"""


def test_a_lock_whose_process_was_killed_is_taken_over(tmp_path: Path) -> None:
    directory = tmp_path / "run.lock"
    child = subprocess.Popen(
        [sys.executable, "-c", HOLDER, str(directory)],
        env=minimal_env(),
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert child.stdout is not None
        word, real_pid = child.stdout.readline().split()
        assert word == "holding"
        with pytest.raises(LockHeld):
            try_acquire(directory, owner(), NO_SLEEP)
        child.kill()
        child.wait()

        result = try_acquire(directory, owner(), NO_SLEEP)

        assert result.taken_over is not None and result.taken_over.previous is not None
        assert result.taken_over.previous.pid == int(real_pid)  # not the venv launcher's pid
        assert result.taken_over.previous.run_id == "child-run"
    finally:
        child.kill()
        child.wait()


RACER = """
import sys, time
from pathlib import Path
from forja.core.locking import LockHeld, LockOwner, try_acquire
directory, go, stop, name = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[4]
while not go.exists():
    time.sleep(0.002)
try:
    try_acquire(directory, LockOwner.current(name))
except LockHeld:
    print("HELD", flush=True)
    raise SystemExit
print("OK", flush=True)
while not stop.exists():
    time.sleep(0.02)
"""


@pytest.mark.parametrize("round_number", range(3))
def test_many_processes_racing_for_an_abandoned_lock_produce_exactly_one_winner(
    tmp_path: Path, round_number: int
) -> None:
    directory = tmp_path / "run.lock"
    write_lock(directory, dead_owner())
    go, stop = tmp_path / "go", tmp_path / "stop"
    racers = [
        subprocess.Popen(
            [sys.executable, "-c", RACER, str(directory), str(go), str(stop), f"racer{i}"],
            env=minimal_env(),
            stdout=subprocess.PIPE,
            text=True,
        )
        for i in range(8)
    ]
    try:
        go.write_text("go")
        answers = []
        for racer in racers:
            assert racer.stdout is not None
            answers.append(racer.stdout.readline().strip())
    finally:
        stop.write_text("stop")
        for racer in racers:
            racer.wait(timeout=30)

    assert sorted(answers) == ["HELD"] * 7 + ["OK"]
    assert not (tmp_path / "run.lock.takeover").exists()
