from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from forja.core.events import EventLog, RunState
from forja.core.events.models import EVENT_ADAPTER, Event, compute_hash
from forja.core.states import ExecutionState, Level, TaskState

RUN = "run1"


class FakeClock:
    def __init__(self) -> None:
        self._now = datetime(2026, 10, 10, tzinfo=UTC)

    def __call__(self) -> datetime:
        self._now += timedelta(milliseconds=1)
        return self._now


def open_log(path: Path, run_id: str = RUN, **kwargs: Any) -> EventLog:
    kwargs.setdefault("clock", FakeClock())
    return EventLog.open(path, run_id, **kwargs)


def create_run(log: EventLog) -> None:
    log.append_transition(Level.EXECUTION, RUN, None, ExecutionState.PREPARING)


def create_task(log: EventLog, task_id: str = "t1") -> None:
    log.append_transition(Level.TASK, task_id, None, TaskState.PENDING, parent_id=RUN)


def to_execution_state(log: EventLog, *path: ExecutionState) -> None:
    """Walk the run through ``path``; the first step starts from the current state."""
    current = log.state.state_of(Level.EXECUTION, RUN)
    for step in path:
        log.append_transition(Level.EXECUTION, RUN, current, step)
        current = step


def build_event(state: RunState, event_type: str = "progress", **overrides: Any) -> Event:
    """A hand-made event for envelope rules the log itself would never produce."""
    body: dict[str, Any] = {
        "schema_version": 1,
        "seq": state.last_seq + 1,
        "time": "2026-10-10T00:00:00.000000Z",
        "run_id": state.run_id,
        "type": event_type,
        "level": "execution",
        "target_id": state.run_id,
        "refs": [],
        "payload": {"kind": "note"},
        "prev": state.last_hash,
    }
    body.update(overrides)
    body["hash"] = compute_hash(body)
    return EVENT_ADAPTER.validate_python(body)
