import json
import logging
from pathlib import Path

import pytest

from forja.core.events import (
    GENESIS_HASH,
    Event,
    EventLog,
    InvalidEvent,
    LogUnusable,
    Ref,
    RefKind,
)
from forja.core.states import ExecutionState, Level
from tests.core.events.support import RUN, create_run, create_task, open_log, to_execution_state


def _three_events(log: EventLog) -> None:
    create_run(log)
    create_task(log)
    to_execution_state(log, ExecutionState.CONFIRMED)


def test_file_is_canonical_jsonl_with_lf_endings_and_a_hash_chain(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    with open_log(path) as log:
        _three_events(log)

    raw = path.read_bytes()
    assert b"\r" not in raw
    lines = raw.split(b"\n")
    assert lines.pop() == b""
    records = [json.loads(line) for line in lines]
    assert [r["seq"] for r in records] == [1, 2, 3]
    assert records[0]["prev"] == GENESIS_HASH
    assert [r["prev"] for r in records[1:]] == [r["hash"] for r in records[:-1]]
    assert all(r["schema_version"] == 1 and r["run_id"] == RUN for r in records)
    assert all(
        json.dumps(r, sort_keys=True, separators=(",", ":")).encode() == line
        for r, line in zip(records, lines, strict=True)
    )


def test_timestamps_are_utc_with_microseconds(tmp_path: Path) -> None:
    with open_log(tmp_path / "events.jsonl") as log:
        event = log.append_transition(Level.EXECUTION, RUN, None, ExecutionState.PREPARING)

    assert event.time == "2026-10-10T00:00:00.001000Z"


def test_reopening_rebuilds_the_same_state(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    with open_log(path) as log:
        _three_events(log)
        log.append_intent(Level.TASK, "t1", "run_tool", "op1")
        before = (log.state.last_seq, log.state.last_hash)

    with open_log(path) as again:
        assert (again.state.last_seq, again.state.last_hash) == before
        assert again.state.state_of(Level.EXECUTION, RUN) is ExecutionState.CONFIRMED
        assert set(again.state.open_operations) == {"op1"}
        again.append_effect(Level.TASK, "t1", "run_tool", "op1")
        assert again.state.last_seq == before[0] + 1


def test_references_are_stored_as_id_and_hash_only(tmp_path: Path) -> None:
    ref = Ref(kind=RefKind.ARTIFACT, id="art1", hash="a" * 64)
    path = tmp_path / "events.jsonl"
    with open_log(path) as log:
        create_run(log)
        log.append_transition(
            Level.EXECUTION, RUN, ExecutionState.PREPARING, ExecutionState.CONFIRMED, refs=[ref]
        )

    last = json.loads(path.read_bytes().splitlines()[-1])
    assert last["refs"] == [{"kind": "artifact", "id": "art1", "hash": "a" * 64}]


def test_fsync_is_skipped_only_for_progress(tmp_path: Path) -> None:
    synced: list[int] = []
    with open_log(tmp_path / "events.jsonl", fsync=synced.append) as log:
        create_run(log)
        assert len(synced) == 1
        log.append_progress(Level.EXECUTION, RUN, "output", payload={"line": "x"})
        assert len(synced) == 1
        log.append_intent(Level.EXECUTION, RUN, "run_tool", "op1")
        log.append_effect(Level.EXECUTION, RUN, "run_tool", "op1")
        assert len(synced) == 3


def test_a_payload_over_the_limit_is_rejected_and_nothing_is_written(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    with open_log(path) as log:
        create_run(log)
        before = path.read_bytes()

        with pytest.raises(InvalidEvent, match="payload is"):
            log.append_progress(Level.EXECUTION, RUN, "output", payload={"line": "x" * 5000})

        assert path.read_bytes() == before


def test_subscribers_see_saved_events_and_a_failing_one_is_isolated(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    seen: list[Event] = []

    def broken(event: Event) -> None:
        raise RuntimeError("ui crashed")

    with open_log(tmp_path / "events.jsonl") as log:
        log.subscribe(broken)
        log.subscribe(seen.append)
        with caplog.at_level(logging.ERROR, logger="forja.events"):
            create_run(log)

        assert [e.seq for e in seen] == [1]
        assert "event subscriber failed" in caplog.text
        assert log.state.last_seq == 1


def test_a_closed_log_refuses_to_write(tmp_path: Path) -> None:
    log = open_log(tmp_path / "events.jsonl")
    log.close()

    with pytest.raises(LogUnusable):
        create_run(log)


def test_a_payload_of_exactly_the_limit_is_accepted(tmp_path: Path) -> None:
    import re  # noqa: PLC0415

    from forja.core.events.models import MAX_PAYLOAD_BYTES  # noqa: PLC0415

    with open_log(tmp_path / "events.jsonl") as log:
        create_run(log)
        # the event adds fields of its own to what is passed: the first refusal tells how many
        with pytest.raises(InvalidEvent, match="payload is") as first:
            log.append_progress(Level.EXECUTION, RUN, "output", payload={"line": "x" * 5000})
        extra = int(re.search(r"payload is (\d+) bytes", str(first.value))[1]) - 5000 - 11  # type: ignore[index]
        room = MAX_PAYLOAD_BYTES - 11 - extra

        log.append_progress(Level.EXECUTION, RUN, "output", payload={"line": "x" * room})

        with pytest.raises(InvalidEvent, match="payload is"):
            log.append_progress(Level.EXECUTION, RUN, "output", payload={"line": "x" * (room + 1)})
