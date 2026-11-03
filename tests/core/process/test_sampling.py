import importlib
import mmap
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from forja.core.process import _sampling
from forja.core.process._sampling import PeakSampler, parse_proc, parse_ps

STAT = "4242 (my (odd) name) S 1 777 777 0 -1 4194304 100 0 0 0 1 1 0 0 20 0 1 0 5 1000 50"


def test_proc_stat_gives_the_group_even_when_the_name_has_parentheses() -> None:
    assert parse_proc(STAT, "250 50 10 5 0 30 0", 4096) == (777, 50 * 4096)


def test_proc_resident_is_in_pages_of_the_given_size() -> None:
    assert parse_proc(STAT, "250 7 10 5 0 30 0", 16384)[1] == 7 * 16384


@pytest.mark.parametrize("stat", ["", "no parenthesis", "1 (x)", "1 (x) S 1"])
def test_a_truncated_proc_stat_is_refused(stat: str) -> None:
    with pytest.raises((ValueError, IndexError)):
        parse_proc(stat, "250 50 10", 4096)


def test_ps_lines_give_group_and_bytes_from_kib() -> None:
    assert parse_ps("  100  2048\n200 1\n") == [(100, 2048 * 1024), (200, 1024)]


def test_ps_ignores_header_and_malformed_lines() -> None:
    assert parse_ps("PGID RSS\n\n100\n100 x\n100 5 6\n-1 5\n300 4\n") == [(300, 4096)]


def test_the_default_snapshot_reads_proc_on_linux_and_ps_elsewhere(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    assert _sampling.default_snapshot() is _sampling.read_proc
    monkeypatch.setattr(sys, "platform", "darwin")
    assert _sampling.default_snapshot() is _sampling.read_ps


class Scripted:
    """A snapshot that returns each prepared reading once, then the last one forever."""

    def __init__(self, *readings: list[tuple[int, int]]) -> None:
        self._readings = list(readings)
        self.calls = 0

    def __call__(self) -> list[tuple[int, int]]:
        self.calls += 1
        return self._readings.pop(0) if len(self._readings) > 1 else self._readings[0]


def test_the_peak_is_the_largest_sum_of_the_group_at_one_moment() -> None:
    snapshot = Scripted(
        [(10, 100), (10, 50), (99, 9999)],
        [(10, 100), (10, 100), (10, 100)],
        [(10, 30)],
    )
    sampler = PeakSampler(10, snapshot, interval=0.001)
    sampler.start()
    while snapshot.calls < 4:
        pass

    assert sampler.stop() == 300


def test_a_group_never_seen_has_no_peak_not_zero() -> None:
    sampler = PeakSampler(10, Scripted([(99, 5000)]), interval=0.001)
    sampler.start()

    assert sampler.stop() is None


def test_a_sampler_never_started_stops_without_a_peak() -> None:
    assert PeakSampler(10, Scripted([(10, 5)])).stop() is None


def test_stopping_twice_keeps_the_peak() -> None:
    sampler = PeakSampler(10, Scripted([(10, 5)]), interval=0.001)
    sampler.start()

    assert sampler.stop() == 5
    assert sampler.stop() == 5


@pytest.mark.skipif(sys.platform == "win32", reason="the group is a POSIX process group")
def test_a_posix_group_reports_the_sampled_peak_of_its_own_pid() -> None:
    posix: Any = importlib.import_module("forja.core.process._posix")
    PosixGroup = posix.PosixGroup

    group = PosixGroup(Scripted([(4321, 700), (1, 5)]))
    group.attach(4321)
    try:
        assert group.peak_memory() == 700
    finally:
        group.close()


@pytest.mark.skipif(sys.platform == "win32", reason="the group is a POSIX process group")
def test_a_posix_group_never_attached_has_no_measure() -> None:
    posix: Any = importlib.import_module("forja.core.process._posix")
    PosixGroup = posix.PosixGroup

    group = PosixGroup(Scripted([(1, 5)]))

    assert group.peak_memory() is None
    group.close()


@pytest.mark.skipif(sys.platform != "linux", reason="reads /proc")
def test_proc_snapshot_sees_this_process_in_its_group() -> None:
    import os

    group = cast(Any, os).getpgrp()
    seen = dict(_sampling.read_proc())

    assert group in seen
    assert seen[group] > 0


@pytest.mark.skipif(sys.platform != "darwin", reason="reads ps")
def test_ps_snapshot_sees_this_process_in_its_group() -> None:
    import os

    mine = cast(Any, os).getpgrp()
    assert any(group == mine and size > 0 for group, size in _sampling.read_ps())


def test_the_sampling_thread_does_not_keep_the_process_alive() -> None:
    assert PeakSampler(10, Scripted([]))._thread.daemon


def test_proc_snapshot_reads_each_numbered_entry_and_skips_the_unreadable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / "7").mkdir()
    (tmp_path / "7" / "stat").write_text(STAT)
    (tmp_path / "7" / "statm").write_text("1000 25 3")
    (tmp_path / "8").mkdir()  # ended between the listing and the read
    (tmp_path / "self").mkdir()
    monkeypatch.setattr(_sampling, "Path", lambda name: tmp_path if name == "/proc" else Path(name))

    assert _sampling.read_proc() == [(777, 25 * mmap.PAGESIZE)]


def test_ps_snapshot_asks_ps_for_group_and_resident_size(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    def fake_run(command: list[str], **options: object) -> SimpleNamespace:
        calls.append((command, options))
        return SimpleNamespace(stdout="  PGID RSS\n 10 4\n")

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert _sampling.read_ps() == [(10, 4096)]
    assert calls == [
        (
            ["ps", "-axo", "pgid=,rss="],
            {"capture_output": True, "text": True, "check": False, "timeout": 5},
        )
    ]


@pytest.mark.parametrize("failure", [OSError("no ps"), subprocess.TimeoutExpired("ps", 5)])
def test_ps_snapshot_is_empty_when_ps_cannot_be_read(
    monkeypatch: pytest.MonkeyPatch, failure: Exception
) -> None:
    def fake_run(command: list[str], **options: object) -> SimpleNamespace:
        raise failure

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert _sampling.read_ps() == []
