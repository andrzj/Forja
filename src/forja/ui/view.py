"""What the screen shows, kept up to date from the events of the run.

The interface decides nothing: it reads the same events that go to the log and keeps this view.
Every renderer (the full screen, the live line, plain text) draws from a snapshot of it, so they
cannot disagree, and a view can be rebuilt after a crash by reading the log again.
"""

import re
import time
from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from enum import StrEnum
from pathlib import Path

from forja.core.events.models import Event
from forja.core.events.versioning import BadLine, parse_line
from forja.core.states import AttemptState, ExecutionState, Level, TaskState
from forja.ui.glyphs import clean

GATES = ("scope", "secrets", "format", "lint", "build", "tests", "complexity", "mutation")
_FEED = 60
_REJECTIONS = 20
_RUN_TOOL = re.compile(r"^run_tool:[^:]+:(?P<check>[a-z_]+):\d+$")
_GATE_OF = re.compile(r"gate \d+ \((?P<check>[a-z_]+)\)")
_ATTEMPT = re.compile(r"-a(?P<number>\d+)$")


class GateStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"


@dataclass(frozen=True)
class FeedLine:
    time: str  # HH:MM:SS
    kind: str  # read, edit, command, text, error, note
    text: str


@dataclass(frozen=True)
class View:
    objective: str
    repo: str
    branch: str
    isolation: str
    state: str
    message: str
    tasks_total: int
    tasks_done: int
    task_id: str
    task_intent: str
    attempt: int
    attempts_max: int
    gates: tuple[tuple[str, GateStatus], ...]
    feed: tuple[FeedLine, ...]
    rejections: tuple[str, ...]
    feed_total: int
    rejections_total: int
    tokens_used: int
    tokens_limit: int
    elapsed: float
    tasks_integrated: int = 0
    tasks_blocked: int = 0
    task_rows: tuple[tuple[str, str, str], ...] = ()  # (id, intent, state), in plan order

    @property
    def tokens_fraction(self) -> float:
        return self.tokens_used / self.tokens_limit if self.tokens_limit else 0.0

    @property
    def finished(self) -> bool:
        return self.state in (
            ExecutionState.DELIVERED,
            ExecutionState.FAILED,
            ExecutionState.PAUSED,
            ExecutionState.DISCARDED,
        )


@dataclass
class ViewModel:
    objective: str
    repo: str
    branch: str
    isolation: str
    token_limit: int
    attempts_max: int
    clock: Callable[[], float] = time.monotonic
    state: str = ExecutionState.PREPARING.value
    message: str = ""
    tasks: dict[str, str] = field(default_factory=dict)  # id -> state
    intents: dict[str, str] = field(default_factory=dict)
    task_id: str = ""
    attempt: int = 0
    gates: dict[str, GateStatus] = field(default_factory=dict)
    feed: deque[FeedLine] = field(default_factory=lambda: deque(maxlen=_FEED))
    rejections: deque[str] = field(default_factory=lambda: deque(maxlen=_REJECTIONS))
    tokens_used: int = 0
    seconds_before: float = 0.0
    feed_total: int = 0
    rejections_total: int = 0

    def __post_init__(self) -> None:
        self.objective, self.repo = clean(self.objective), clean(self.repo)
        self.branch, self.isolation = clean(self.branch), clean(self.isolation)
        self._started = self.clock()
        self._reset_gates()

    # -- reading the events -------------------------------------------------------------------

    def replay(self, path: Path) -> None:
        """Take in everything already in the log (a resumed run starts from where it was)."""
        if not path.exists():
            return
        for raw in [line for line in path.read_bytes().split(b"\n") if line]:
            try:
                self.apply(parse_line(raw))
            except BadLine:
                break

    def apply(self, event: Event) -> None:
        if event.type == "transition":
            self._transition(event.level, event.target_id, event.to_state, event.payload)
        elif event.type in ("intent", "effect"):
            self._tool(event.type, event.operation, event.operation_id)
        elif event.type == "progress":
            self._progress(event.time, event.payload)

    def _transition(
        self, level: Level, target: str, to: str, payload: Mapping[str, object]
    ) -> None:
        if level is Level.EXECUTION:
            self.state = to
            reason = payload.get("reason")
            self.message = clean(str(reason)) if reason else ""
        elif level is Level.TASK:
            self.tasks[target] = to
            if "intent" in payload:
                self.intents[target] = clean(str(payload["intent"]))
            if to == TaskState.IN_PROGRESS.value:
                self.task_id = target
                self.attempt = 0
                self._reset_gates()
        elif level is Level.ATTEMPT:
            self._attempt(target, to, payload)

    def _attempt(self, target: str, to: str, payload: Mapping[str, object]) -> None:
        found = _ATTEMPT.search(target)
        if to == AttemptState.CREATED.value:
            self.attempt = int(found["number"]) if found else self.attempt + 1
            self._reset_gates()
        elif to == AttemptState.APPROVED.value:
            self.gates = dict.fromkeys(GATES, GateStatus.PASSED)
        elif to == AttemptState.REJECTED.value:
            reason = str(payload.get("reason", ""))
            self._mark_failed(reason)
            self._reject(f"{target}: {reason}")
        elif to == AttemptState.DISCARDED.value:
            self._reject(f"{target}: {payload.get('reason', 'discarded')}")

    def _mark_failed(self, reason: str) -> None:
        found = _GATE_OF.search(reason)
        if found and found["check"] in self.gates:
            self._advance_to(found["check"], GateStatus.FAILED)

    def _tool(self, kind: str, operation: str, operation_id: str) -> None:
        found = _RUN_TOOL.match(operation_id) if operation == "run_tool" else None
        if not found:
            return
        check = found["check"].removesuffix("_before")
        if check in self.gates and kind == "intent":
            self._advance_to(check, GateStatus.RUNNING)

    def _advance_to(self, check: str, status: GateStatus) -> None:
        """The pipeline is in order and stops at the first failure: what came before passed."""
        reached = False
        for gate in GATES:
            if gate == check:
                self.gates[gate] = status
                reached = True
            elif not reached and self.gates[gate] is not GateStatus.FAILED:
                self.gates[gate] = GateStatus.PASSED

    def _progress(self, moment: str, payload: Mapping[str, object]) -> None:
        kind = payload.get("kind")
        clock = moment[11:19]
        if kind == "agent_activity":
            self._activity(clock, payload)
        elif kind == "waiting_for_network":
            self._add(FeedLine(clock, "note", "aguardando a rede voltar"))
        elif kind == "session_started":
            self.message = ""

    def _activity(self, clock: str, payload: Mapping[str, object]) -> None:
        kind = payload.get("type")
        if kind == "usage":
            self.tokens_used += _count(payload.get("input")) + _count(payload.get("output"))
        elif kind == "file_read":
            self._add(FeedLine(clock, "read", f"leu {payload.get('path', '')}"))
        elif kind == "file_edit":
            added, removed = _count(payload.get("added")), _count(payload.get("removed"))
            text = f"editou {payload.get('path', '')} (+{added} -{removed})"
            self._add(FeedLine(clock, "edit", text))
        elif kind == "command":
            self._add(FeedLine(clock, "command", f"rodou {payload.get('command', '')}"))
        elif kind == "text":
            self._add(FeedLine(clock, "text", str(payload.get("text", ""))))
        elif kind == "error":
            self._add(FeedLine(clock, "error", str(payload.get("message", ""))))

    def _add(self, line: FeedLine) -> None:
        self.feed.append(replace(line, text=clean(line.text)))
        self.feed_total += 1

    def _reject(self, text: str) -> None:
        self.rejections.append(clean(text))
        self.rejections_total += 1

    def _reset_gates(self) -> None:
        self.gates = dict.fromkeys(GATES, GateStatus.PENDING)

    # -- what the screen asks for -------------------------------------------------------------

    def snapshot(self) -> View:
        done = sum(1 for s in self.tasks.values() if s in (TaskState.INTEGRATED, TaskState.BLOCKED))
        return View(
            objective=self.objective,
            repo=self.repo,
            branch=self.branch,
            isolation=self.isolation,
            state=self.state,
            message=self.message,
            tasks_total=len(self.tasks),
            tasks_done=done,
            task_id=self.task_id,
            task_intent=self.intents.get(self.task_id, ""),
            attempt=self.attempt,
            attempts_max=self.attempts_max,
            gates=tuple(self.gates.items()),
            feed=tuple(self.feed),
            rejections=tuple(self.rejections),
            feed_total=self.feed_total,
            rejections_total=self.rejections_total,
            tokens_used=self.tokens_used,
            tokens_limit=self.token_limit,
            elapsed=self.seconds_before + (self.clock() - self._started),
            tasks_integrated=sum(1 for s in self.tasks.values() if s == TaskState.INTEGRATED),
            tasks_blocked=sum(1 for s in self.tasks.values() if s == TaskState.BLOCKED),
            task_rows=tuple(
                (task, self.intents.get(task, ""), state) for task, state in self.tasks.items()
            ),
        )


def _count(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else 0


def blank_view(**changes: object) -> View:
    """A view with nothing in it, for tests and for the first frame."""
    base = View("", "", "", "", "preparing", "", 0, 0, "", "", 0, 0, (), (), (), 0, 0, 0, 0, 0.0)
    return replace(base, **changes)  # type: ignore[arg-type]
