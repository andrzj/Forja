import logging
import os
from collections.abc import Callable, Iterable, Mapping
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Self

from pydantic import JsonValue, ValidationError

from forja.core.atomic import atomic_write_bytes
from forja.core.events.errors import CorruptLogError, InvalidEvent, LogUnusable
from forja.core.events.models import (
    EVENT_ADAPTER,
    SCHEMA_VERSION,
    Event,
    Ref,
    canonical_json,
    compute_hash,
    format_time,
)
from forja.core.events.state import RunState
from forja.core.events.versioning import UPGRADERS, BadLine, Upgrader, parse_line
from forja.core.states import InvalidTransition, Level

_logger = logging.getLogger("forja.events")
_O_BINARY = getattr(os, "O_BINARY", 0)

Subscriber = Callable[[Event], None]


def _utc_now() -> datetime:
    return datetime.now(UTC)


class EventLog:
    """Append-only JSONL event log of one run, and the only writer of its state.

    Each line is a canonical JSON event whose ``prev`` is the hash of the line before it. An event
    is validated against the run state before anything is written, so the log never contains an
    event the rules reject. Subscribers (such as the terminal UI) see events after they are saved;
    a failing subscriber never affects the log.

    Any failure while writing makes the log unusable, because the file may end in a partial line.
    Discard it and call ``open`` again: the state is whatever the file holds, and the partial line,
    if any, is recovered.
    """

    def __init__(
        self,
        path: Path,
        state: RunState,
        fd: int,
        clock: Callable[[], datetime],
        write: Callable[[int, bytes], int],
        fsync: Callable[[int], None],
    ) -> None:
        self.path = path
        self.state = state
        self._fd: int | None = fd
        self._clock = clock
        self._write = write
        self._fsync = fsync
        self._unusable = False
        self._subscribers: list[Subscriber] = []

    @classmethod
    def open(
        cls,
        path: Path,
        run_id: str,
        *,
        clock: Callable[[], datetime] = _utc_now,
        write: Callable[[int, bytes], int] = os.write,
        fsync: Callable[[int], None] = os.fsync,
        upgraders: Mapping[int, Upgrader] = UPGRADERS,
    ) -> Self:
        """Open or create the log, rebuilding the state and recovering from a torn last line."""
        path.parent.mkdir(parents=True, exist_ok=True)
        data = path.read_bytes() if path.exists() else b""
        state = RunState(run_id)
        good_end, discarded, needs_newline = _replay(data, state, upgraders)

        if discarded is not None:
            sidecar = _next_sidecar(path)
            atomic_write_bytes(sidecar, discarded)
            with path.open("r+b") as handle:
                handle.truncate(good_end)
                handle.flush()
                fsync(handle.fileno())
        fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | _O_BINARY, 0o644)
        log = cls(path, state, fd, clock, write, fsync)
        try:
            if needs_newline:
                log._write_all(b"\n")
                fsync(fd)
            if discarded is not None:
                log.append_progress(
                    Level.EXECUTION,
                    run_id,
                    "tail_discarded",
                    payload={"bytes": len(discarded), "sidecar": sidecar.name},
                )
        except BaseException:
            os.close(fd)
            raise
        return log

    def subscribe(self, subscriber: Subscriber) -> None:
        self._subscribers.append(subscriber)

    def close(self) -> None:
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def append_transition(
        self,
        level: Level,
        target_id: str,
        from_state: StrEnum | None,
        to_state: StrEnum,
        *,
        parent_id: str | None = None,
        refs: Iterable[Ref] = (),
        payload: Mapping[str, JsonValue] | None = None,
    ) -> Event:
        return self._append(
            "transition",
            level,
            target_id,
            refs,
            payload,
            from_state=None if from_state is None else from_state.value,
            to_state=to_state.value,
            parent_id=parent_id,
        )

    def append_intent(
        self,
        level: Level,
        target_id: str,
        operation: str,
        operation_id: str,
        *,
        refs: Iterable[Ref] = (),
        payload: Mapping[str, JsonValue] | None = None,
    ) -> Event:
        return self._append(
            "intent",
            level,
            target_id,
            refs,
            payload,
            operation=operation,
            operation_id=operation_id,
        )

    def append_effect(
        self,
        level: Level,
        target_id: str,
        operation: str,
        operation_id: str,
        *,
        refs: Iterable[Ref] = (),
        payload: Mapping[str, JsonValue] | None = None,
    ) -> Event:
        return self._append(
            "effect",
            level,
            target_id,
            refs,
            payload,
            operation=operation,
            operation_id=operation_id,
        )

    def append_progress(
        self,
        level: Level,
        target_id: str,
        kind: str,
        *,
        operation: str | None = None,
        operation_id: str | None = None,
        payload: Mapping[str, JsonValue] | None = None,
    ) -> Event:
        return self._append(
            "progress",
            level,
            target_id,
            (),
            {**(payload or {}), "kind": kind},
            operation=operation,
            operation_id=operation_id,
        )

    def _append(
        self,
        event_type: str,
        level: Level,
        target_id: str,
        refs: Iterable[Ref],
        payload: Mapping[str, JsonValue] | None,
        **fields: Any,
    ) -> Event:
        if self._unusable or self._fd is None:
            raise LogUnusable("an earlier write failed or the log is closed; reopen it")
        state = self.state
        body: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "seq": state.last_seq + 1,
            "time": format_time(self._clock()),
            "run_id": state.run_id,
            "type": event_type,
            "level": level.value,
            "target_id": target_id,
            "refs": [ref.model_dump(mode="json") for ref in refs],
            "payload": dict(payload or {}),
            "prev": state.last_hash,
            **fields,
        }
        body["hash"] = compute_hash(body)
        try:
            event = EVENT_ADAPTER.validate_python(body)
        except ValidationError as error:
            raise InvalidEvent(error.errors()[0]["msg"]) from None
        state.validate(event)

        line = canonical_json(event.model_dump(mode="json")) + b"\n"
        try:
            self._write_all(line)
            if event_type != "progress":
                self._fsync(self._fd)
        except BaseException:
            self._unusable = True
            raise
        state.apply(event)
        self._notify(event)
        return event

    def _write_all(self, data: bytes) -> None:
        assert self._fd is not None
        view = memoryview(data)
        while view:
            written = self._write(self._fd, bytes(view))
            if written <= 0:
                raise OSError("write made no progress")
            view = view[written:]

    def _notify(self, event: Event) -> None:
        for subscriber in self._subscribers:
            try:
                subscriber(event)
            except Exception:
                _logger.exception("event subscriber failed")


def _replay(
    data: bytes, state: RunState, upgraders: Mapping[int, Upgrader]
) -> tuple[int, bytes | None, bool]:
    """Apply every stored line to ``state``.

    Returns the offset where the good data ends, the torn tail to discard (if any), and whether
    the last line is valid but lacks its newline. Only an unfinished last line may be dropped;
    damage anywhere else refuses the resume.
    """
    offset, line_number = 0, 0
    while offset < len(data):
        newline = data.find(b"\n", offset)
        complete = newline != -1
        end = newline if complete else len(data)
        line_number += 1
        try:
            event = parse_line(data[offset:end], upgraders)
        except BadLine as bad:
            if complete:
                raise CorruptLogError(line_number, str(bad)) from None
            return offset, data[offset:], False
        try:
            state.apply(event)
        except (InvalidEvent, InvalidTransition) as error:
            raise CorruptLogError(line_number, str(error)) from error
        if not complete:
            return len(data), None, True
        offset = end + 1
    return len(data), None, False


def _next_sidecar(path: Path) -> Path:
    number = 1
    while (candidate := path.with_name(f"{path.name}.discarded-{number}")).exists():
        number += 1
    return candidate
