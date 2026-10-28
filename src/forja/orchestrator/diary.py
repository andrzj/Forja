"""The log book of a task: what each attempt said and how it ended, read from the log.

A projection of the run state, like the summary: nothing is written, so a resumed run, or a log cut
short, gives the same entries as a run that was never interrupted. The agent's own words are those
the cycle kept when it moved the attempt to validating; the outcome is the transition that ended it.
"""

from dataclasses import dataclass
from enum import StrEnum

from forja.core.events.state import RunState
from forja.core.states import AttemptState, Level, StageState, TaskState


class Outcome(StrEnum):
    REJECTED = "rejected"
    APPROVED = "approved"
    DISCARDED = "discarded"
    OPEN = "open"  # the attempt has not ended: it is the one running, or the run was cut here


@dataclass(frozen=True)
class Entry:
    """One attempt: what the agent said and how the Forja judged it.

    ``detail`` is the reason of a rejection or of a discard, or the gates an approval passed,
    joined by commas. ``infrastructure`` marks a discard the agent did not cause.
    """

    stage: str
    attempt: str
    said: str
    outcome: Outcome
    detail: str = ""
    infrastructure: bool = False


@dataclass(frozen=True)
class Decision:
    """Something the Forja decided about a stage or a task, with the reason it recorded."""

    target: str
    what: str
    reason: str


EXHAUSTED = "stage_exhausted"
BLOCKED = "task_blocked"


def stage_entries(state: RunState, stage: str) -> list[Entry]:
    return [_entry(state, stage, attempt) for attempt in state.children_of(Level.ATTEMPT, stage)]


def task_entries(state: RunState, task: str) -> list[Entry]:
    return [
        entry
        for stage in state.children_of(Level.STAGE, task)
        for entry in stage_entries(state, stage)
    ]


def task_decisions(state: RunState, task: str) -> list[Decision]:
    found = []
    for stage in state.children_of(Level.STAGE, task):
        if state.state_of(Level.STAGE, stage) is StageState.EXHAUSTED:
            payload = state.transition_payload(Level.STAGE, stage, StageState.EXHAUSTED) or {}
            found.append(Decision(stage, EXHAUSTED, _text(payload.get("reason"))))
    if state.state_of(Level.TASK, task) is TaskState.BLOCKED:
        payload = state.transition_payload(Level.TASK, task, TaskState.BLOCKED) or {}
        found.append(Decision(task, BLOCKED, _text(payload.get("reason"))))
    return found


def _entry(state: RunState, stage: str, attempt: str) -> Entry:
    def entered(to: AttemptState) -> dict[str, object] | None:
        return state.transition_payload(Level.ATTEMPT, attempt, to)  # type: ignore[return-value]

    said = _text((entered(AttemptState.VALIDATING) or {}).get("reason"))
    rejected, discarded, approved = (
        entered(AttemptState.REJECTED),
        entered(AttemptState.DISCARDED),
        entered(AttemptState.APPROVED),
    )
    if rejected is not None:
        return Entry(stage, attempt, said, Outcome.REJECTED, _text(rejected.get("reason")))
    if discarded is not None:
        return Entry(
            stage,
            attempt,
            said,
            Outcome.DISCARDED,
            _text(discarded.get("reason")),
            infrastructure=discarded.get("infra_failure") is True,
        )
    if approved is not None:
        passed = approved.get("gates_passed")
        gates = ", ".join(str(g) for g in passed) if isinstance(passed, list) else ""
        return Entry(stage, attempt, said, Outcome.APPROVED, gates)
    return Entry(stage, attempt, said, Outcome.OPEN)


def _text(value: object) -> str:
    return "" if value is None else str(value)
