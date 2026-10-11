from datetime import UTC, datetime, timedelta
from pathlib import Path

from forja.core.events import EventLog
from forja.core.states import AttemptState, Level, StageState, TaskState
from tests.core.events.support import RUN, create_run

START = datetime(2026, 10, 10, 12, 0, tzinfo=UTC)


class ManualClock:
    """A clock the test moves; each event reads it, so the log shows exactly the gaps we make."""

    def __init__(self) -> None:
        self.now = START

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


def open_with(clock: ManualClock, path: Path) -> EventLog:
    return EventLog.open(path, RUN, clock=clock)


def start_stage(log: EventLog) -> None:
    create_run(log)
    log.append_transition(Level.TASK, "t1", None, TaskState.PENDING, parent_id=RUN)
    log.append_transition(Level.STAGE, "s1", None, StageState.PENDING, parent_id="t1")


def add_attempt(
    log: EventLog, attempt_id: str, end: AttemptState, *, infra_failure: bool | None = None
) -> None:
    """Walk a new attempt of stage s1 to ``end`` (rejected, committed or discarded)."""
    log.append_transition(Level.ATTEMPT, attempt_id, None, AttemptState.CREATED, parent_id="s1")
    path = [AttemptState.WORKCOPY_READY, AttemptState.AGENT_RUNNING]
    if end is AttemptState.COMMITTED:
        path += [AttemptState.VALIDATING, AttemptState.APPROVED]
    elif end is AttemptState.REJECTED:
        path += [AttemptState.VALIDATING]
    current = AttemptState.CREATED
    for step in path:
        log.append_transition(Level.ATTEMPT, attempt_id, current, step)
        current = step
    payload = {} if infra_failure is None else {"infra_failure": infra_failure}
    log.append_transition(Level.ATTEMPT, attempt_id, current, end, payload=payload)
