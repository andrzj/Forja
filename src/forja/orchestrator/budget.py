"""What an execution has used so far, read from its events.

There is no separate file for this: a resumed process reads the log again and gets the same
answer. Time is the sum of the sessions (``session_started`` up to ``session_ended``, or up to the
last event when the process died), so the hours a run spent paused do not count.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from forja.core.events.models import Event
from forja.core.events.state import RunState
from forja.core.events.versioning import BadLine, parse_line
from forja.core.states import AttemptState, Level

SESSION_STARTED = "session_started"
SESSION_ENDED = "session_ended"
AGENT_ACTIVITY = "agent_activity"
USAGE = "usage"


@dataclass(frozen=True)
class Consumption:
    seconds: float
    tokens: int


def _moment(event: Event) -> datetime:
    return datetime.fromisoformat(event.time)


def read_consumption(log_path: Path) -> Consumption:
    """Time and tokens spent according to the log; a torn last line is ignored."""
    if not log_path.exists():
        return Consumption(0.0, 0)
    seconds = 0.0
    tokens = 0
    started: datetime | None = None
    last: datetime | None = None  # read only after the first event sets it
    for raw in [line for line in log_path.read_bytes().split(b"\n") if line]:
        try:
            event = parse_line(raw)
        except BadLine:
            break
        moment = _moment(event)
        kind = event.payload.get("kind")
        if event.type == "progress" and kind == SESSION_STARTED:
            if started is not None and last is not None:
                seconds += (last - started).total_seconds()  # the earlier session never ended
            started = moment
        elif event.type == "progress" and kind == SESSION_ENDED and started is not None:
            seconds += (moment - started).total_seconds()
            started = None
        elif (
            event.type == "progress"
            and kind == AGENT_ACTIVITY
            and event.payload.get("type") == USAGE
        ):
            tokens += _count(event.payload.get("input")) + _count(event.payload.get("output"))
        last = moment
    if started is not None and last is not None:
        seconds += (last - started).total_seconds()
    return Consumption(seconds, tokens)


def _count(value: object) -> int:
    return max(0, value) if isinstance(value, int) and not isinstance(value, bool) else 0


class Meter:
    """The time budget of this process: what earlier sessions used plus what this one has."""

    def __init__(
        self,
        limit_seconds: float,
        spent_before: Consumption,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._limit = limit_seconds
        self._before = spent_before.seconds
        self._clock = clock
        self._started = clock()

    def elapsed(self) -> float:
        return self._before + (self._clock() - self._started)

    def remaining(self) -> float:
        return max(0.0, self._limit - self.elapsed())

    def exhausted(self) -> bool:
        return self.elapsed() >= self._limit


_COUNTED = (AttemptState.REJECTED, AttemptState.APPROVED, AttemptState.COMMITTED)


def quality_attempts(state: RunState, stage_id: str) -> int:
    """Attempts that judged the agent's work; discarded ones measure instability, not quality."""
    return sum(
        state.state_of(Level.ATTEMPT, attempt) in _COUNTED
        for attempt in state.children_of(Level.ATTEMPT, stage_id)
    )


def consecutive_infra_failures(state: RunState, stage_id: str) -> int:
    """Infrastructure failures at the end of the stage's attempts, with nothing else after them."""
    count = 0
    for attempt in reversed(state.children_of(Level.ATTEMPT, stage_id)):
        if state.state_of(Level.ATTEMPT, attempt) is not AttemptState.DISCARDED:
            break
        payload = state.transition_payload(Level.ATTEMPT, attempt, AttemptState.DISCARDED) or {}
        if payload.get("infra_failure") is not True:
            break
        count += 1
    return count
