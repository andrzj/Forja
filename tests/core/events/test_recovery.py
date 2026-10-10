"""Torn tails, corruption, schema versions and injected I/O failures."""

import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from forja.core.events import (
    CorruptLogError,
    EventLog,
    LogUnusable,
    UnsupportedSchemaVersion,
)
from forja.core.events.models import compute_hash
from forja.core.states import ExecutionState, Level
from tests.core.events.support import RUN, create_run, create_task, open_log, to_execution_state

E = ExecutionState


def _write_three(path: Path) -> list[bytes]:
    with open_log(path) as log:
        create_run(log)
        create_task(log)
        to_execution_state(log, E.CONFIRMED)
    return path.read_bytes().splitlines(keepends=True)


def _signature(log: EventLog) -> tuple[int, str]:
    return log.state.last_seq, log.state.last_hash


def _kinds(path: Path) -> list[tuple[str, str]]:
    records = [json.loads(line) for line in path.read_bytes().splitlines()]
    return [(r["type"], r["payload"].get("kind", "")) for r in records]


# -- torn tail ---------------------------------------------------------------------------------


def test_every_possible_cut_of_the_last_line_is_recovered(tmp_path: Path) -> None:
    source = tmp_path / "source.jsonl"
    lines = _write_three(source)
    head = b"".join(lines[:2])
    last = lines[2]
    with open_log(tmp_path / "reference.jsonl") as reference:
        create_run(reference)
        create_task(reference)
        expected = _signature(reference)

    for cut in range(1, len(last) - 1):  # every strict prefix of the last line, newline excluded
        path = tmp_path / f"cut{cut}.jsonl"
        path.write_bytes(head + last[:cut])

        with open_log(path) as log:
            assert log.state.state_of(Level.EXECUTION, RUN) is E.PREPARING, cut
            assert log.state.children_of(Level.TASK, RUN) == ["t1"], cut
            assert log.state.last_seq == expected[0] + 1, cut  # the notice takes the next seq

        sidecar = path.with_name(path.name + ".discarded-1")
        assert sidecar.read_bytes() == last[:cut], cut
        assert _kinds(path)[-1] == ("progress", "tail_discarded"), cut
        with open_log(path) as again:  # the repaired file reopens cleanly
            assert not path.with_name(path.name + ".discarded-2").exists()
            assert again.state.last_seq == expected[0] + 1


def test_a_complete_last_line_missing_only_its_newline_is_kept(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    lines = _write_three(path)
    path.write_bytes(b"".join(lines)[:-1])

    with open_log(path) as log:
        assert log.state.state_of(Level.EXECUTION, RUN) is E.CONFIRMED
        assert log.state.last_seq == 3
        log.append_progress(Level.EXECUTION, RUN, "note")

    assert path.read_bytes().endswith(b"\n")
    assert not path.with_name("events.jsonl.discarded-1").exists()
    with open_log(path) as again:
        assert again.state.last_seq == 4


def test_a_torn_first_line_leaves_an_empty_run(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    lines = _write_three(path)
    path.write_bytes(lines[0][:20])

    with open_log(path) as log:
        assert not log.state.has_target(Level.EXECUTION, RUN)
        assert log.state.last_seq == 1
        create_run(log)  # the run can be created again


def test_each_recovery_gets_its_own_sidecar(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    for round_ in (1, 2):
        lines = _write_three(path) if round_ == 1 else path.read_bytes().splitlines(keepends=True)
        path.write_bytes(b"".join(lines) + b'{"torn')
        open_log(path).close()

    assert path.with_name("events.jsonl.discarded-1").read_bytes() == b'{"torn'
    assert path.with_name("events.jsonl.discarded-2").read_bytes() == b'{"torn'


# -- corruption elsewhere ----------------------------------------------------------------------


def _expect_corrupt(path: Path, line: int) -> None:
    before = path.read_bytes()
    with pytest.raises(CorruptLogError) as info:
        open_log(path)
    assert info.value.line == line
    assert path.read_bytes() == before  # a refused log is never modified


def test_an_edited_line_in_the_middle_is_detected(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    lines = _write_three(path)
    lines[1] = lines[1].replace(b'"t1"', b'"t2"')
    path.write_bytes(b"".join(lines))

    _expect_corrupt(path, 2)


def test_an_edited_last_complete_line_is_corruption_not_a_torn_tail(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    lines = _write_three(path)
    lines[2] = lines[2].replace(b"confirmed", b"executing")
    path.write_bytes(b"".join(lines))

    _expect_corrupt(path, 3)


def test_a_removed_line_breaks_the_chain(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    lines = _write_three(path)
    path.write_bytes(lines[0] + lines[2])

    _expect_corrupt(path, 2)


def test_swapped_lines_are_detected(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    lines = _write_three(path)
    path.write_bytes(lines[0] + lines[2] + lines[1])

    _expect_corrupt(path, 2)


def test_garbage_followed_by_a_newline_is_corruption(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    lines = _write_three(path)
    path.write_bytes(b"".join(lines) + b"garbage\n")

    _expect_corrupt(path, 4)


def _forged(path: Path, lines: list[bytes], **changes: Any) -> None:
    """Replace the last line by one with a valid hash but different content."""
    record = json.loads(lines[-1])
    record.update(changes)
    del record["hash"]
    record["hash"] = compute_hash(record)
    text = json.dumps(record, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    path.write_bytes(b"".join(lines[:-1]) + text)


def test_a_line_with_a_valid_hash_that_breaks_the_rules_is_corruption(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    lines = _write_three(path)
    _forged(path, lines, from_state="preparing", to_state="delivered")

    _expect_corrupt(path, 3)


# -- schema versions ---------------------------------------------------------------------------


def test_a_newer_schema_version_is_refused_not_misread(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    lines = _write_three(path)
    record = json.loads(lines[-1])
    record["schema_version"] = 2
    path.write_bytes(b"".join(lines[:-1]) + json.dumps(record).encode() + b"\n")
    before = path.read_bytes()

    with pytest.raises(UnsupportedSchemaVersion) as info:
        open_log(path)

    assert info.value.version == 2
    assert "upgrade Forja" in str(info.value)
    assert path.read_bytes() == before


def _v0_line(prev: str) -> bytes:
    """A made-up version 0 record that called ``target_id`` simply ``target``."""
    body: dict[str, Any] = {
        "schema_version": 0,
        "seq": 1,
        "time": "2026-10-10T00:00:00.000000Z",
        "run_id": RUN,
        "type": "transition",
        "level": "execution",
        "target": RUN,
        "from_state": None,
        "to_state": "preparing",
        "prev": prev,
    }
    body["hash"] = compute_hash(body)
    return json.dumps(body, sort_keys=True, separators=(",", ":")).encode() + b"\n"


def _upgrade_v0(record: dict[str, Any]) -> dict[str, Any]:
    upgraded = dict(record)
    upgraded["target_id"] = upgraded.pop("target")
    return upgraded


def test_older_records_are_converted_when_read_and_the_chain_still_holds(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    path.write_bytes(_v0_line("0" * 64))

    with open_log(path, upgraders={0: _upgrade_v0}) as log:
        assert log.state.state_of(Level.EXECUTION, RUN) is E.PREPARING
        to_execution_state(log, E.CONFIRMED)  # new records chain onto the old hash

    with open_log(path, upgraders={0: _upgrade_v0}) as again:
        assert again.state.state_of(Level.EXECUTION, RUN) is E.CONFIRMED


def test_an_older_record_without_a_converter_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    path.write_bytes(_v0_line("0" * 64))

    with pytest.raises(UnsupportedSchemaVersion):
        open_log(path, upgraders={})


def test_a_tampered_old_record_is_caught_before_conversion(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    path.write_bytes(_v0_line("0" * 64).replace(b"preparing", b"confirmed"))

    with pytest.raises(CorruptLogError):
        open_log(path, upgraders={0: _upgrade_v0})


# -- injected I/O failures ---------------------------------------------------------------------


class _Fault:
    """Write/fsync pair that fails on the n-th call of a chosen kind."""

    def __init__(self, kind: str, nth: int, *, partial: int | None = None) -> None:
        self.kind, self.nth, self.partial = kind, nth, partial
        self.writes = self.syncs = 0

    def write(self, fd: int, data: bytes) -> int:
        self.writes += 1
        if self.kind == "write" and self.writes == self.nth:
            if self.partial:
                os.write(fd, data[: self.partial])
            raise OSError("disk full")
        return os.write(fd, data)

    def fsync(self, fd: int) -> None:
        self.syncs += 1
        if self.kind == "fsync" and self.syncs == self.nth:
            raise OSError("fsync failed")
        os.fsync(fd)


def test_a_failed_write_makes_the_log_unusable_and_reopening_restores_the_last_good_state(
    tmp_path: Path,
) -> None:
    path = tmp_path / "events.jsonl"
    fault = _Fault("write", 2)
    log = open_log(path, write=fault.write, fsync=fault.fsync)
    create_run(log)
    before = path.read_bytes()

    with pytest.raises(OSError, match="disk full"):
        create_task(log)
    with pytest.raises(LogUnusable):
        create_task(log)
    log.close()

    assert path.read_bytes() == before
    with open_log(path) as again:
        assert again.state.last_seq == 1
        create_task(again)


def test_a_half_written_line_is_discarded_on_reopen(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    fault = _Fault("write", 2, partial=25)
    log = open_log(path, write=fault.write, fsync=fault.fsync)
    create_run(log)

    with pytest.raises(OSError):
        create_task(log)
    log.close()

    with open_log(path) as again:
        assert not again.state.has_target(Level.TASK, "t1")
        assert path.with_name("events.jsonl.discarded-1").stat().st_size == 25


def test_a_failed_fsync_after_a_full_write_keeps_the_event_and_the_log_must_be_reopened(
    tmp_path: Path,
) -> None:
    path = tmp_path / "events.jsonl"
    fault = _Fault("fsync", 2)
    log = open_log(path, write=fault.write, fsync=fault.fsync)
    create_run(log)

    with pytest.raises(OSError, match="fsync failed"):
        create_task(log)
    with pytest.raises(LogUnusable):
        create_task(log)
    log.close()

    with open_log(path) as again:  # what the file holds is the truth
        assert again.state.has_target(Level.TASK, "t1")


def test_short_writes_are_completed(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"

    def dribble(fd: int, data: bytes) -> int:
        return os.write(fd, data[:7])

    with open_log(path, write=dribble) as log:
        create_run(log)
        create_task(log)

    with open_log(path) as again:
        assert again.state.last_seq == 2


def test_a_write_that_makes_no_progress_is_an_error(tmp_path: Path) -> None:
    with (
        open_log(tmp_path / "events.jsonl", write=lambda fd, data: 0) as log,
        pytest.raises(OSError, match="no progress"),
    ):
        create_run(log)


# -- resuming after an interruption at every step boundary -------------------------------------

Step = tuple[Callable[[EventLog], object], Callable[[EventLog], bool]]


def _scenario() -> list[Step]:
    """Steps of a small run; each pairs the action with a check that it already happened."""

    def reached(level: Level, target: str, *states: Any) -> Callable[[EventLog], bool]:
        """True once the target is in one of ``states``: the step or a later one happened."""
        return lambda log: (
            log.state.has_target(level, target) and log.state.state_of(level, target) in states
        )

    def op(name: str) -> Callable[[EventLog], bool]:
        return lambda log: name in log.state._closed  # noqa: SLF001

    return [
        (create_run, lambda log: log.state.has_target(Level.EXECUTION, RUN)),
        (
            lambda log: to_execution_state(log, E.CONFIRMED),
            reached(Level.EXECUTION, RUN, E.CONFIRMED, E.MEASURING_BASELINE),
        ),
        (create_task, lambda log: log.state.has_target(Level.TASK, "t1")),
        (
            lambda log: log.append_intent(Level.TASK, "t1", "run_tool", "op1"),
            lambda log: "op1" in log.state.open_operations or op("op1")(log),
        ),
        (
            lambda log: log.append_effect(Level.TASK, "t1", "run_tool", "op1"),
            op("op1"),
        ),
        (
            lambda log: to_execution_state(log, E.MEASURING_BASELINE),
            reached(Level.EXECUTION, RUN, E.MEASURING_BASELINE),
        ),
    ]


def _run_steps(log: EventLog, steps: list[Step]) -> None:
    for action, done in steps:
        if not done(log):
            action(log)


def _facts(path: Path) -> list[tuple[Any, ...]]:
    """Everything a resume cares about; progress events are display-only."""
    out = []
    for line in path.read_bytes().splitlines():
        r = json.loads(line)
        if r["type"] != "progress":
            out.append(
                (
                    r["type"],
                    r["level"],
                    r["target_id"],
                    r.get("from_state"),
                    r.get("to_state"),
                    r.get("operation_id"),
                )
            )
    return out


@pytest.mark.parametrize("fault_kind", ["write", "fsync"])
@pytest.mark.parametrize("partial", [None, 1, 40])
def test_interrupting_any_append_and_resuming_reaches_the_same_events(
    tmp_path: Path, fault_kind: str, partial: int | None
) -> None:
    if fault_kind == "fsync" and partial is not None:
        pytest.skip("partial only applies to writes")
    steps = _scenario()
    reference = tmp_path / "reference.jsonl"
    with open_log(reference) as log:
        _run_steps(log, steps)
    expected = _facts(reference)

    appends = len(reference.read_bytes().splitlines())
    for nth in range(1, appends + 1):
        path = tmp_path / f"{fault_kind}-{partial}-{nth}.jsonl"
        fault = _Fault(fault_kind, nth, partial=partial)
        log = open_log(path, write=fault.write, fsync=fault.fsync)
        with pytest.raises(OSError):
            _run_steps(log, steps)
        log.close()

        with open_log(path) as resumed:  # new process: recover, then continue
            _run_steps(resumed, steps)

        assert _facts(path) == expected, (fault_kind, partial, nth)
