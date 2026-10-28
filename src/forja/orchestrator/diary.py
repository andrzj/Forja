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


FULL_ENTRIES = 3  # the latest attempts of a stage that are shown in full
SAID_CUT = 300
LINE_CUT = 160
DIARY_LIMIT = 6000


def diary_text(entries: list[Entry]) -> str:
    """The earlier attempts of a stage, as the agent is shown them; empty when there are none.

    The latest ``FULL_ENTRIES`` rejected or unfinished attempts keep what the agent said and why
    the work was turned down; the older ones, and every discard, are one line. Past
    ``DIARY_LIMIT`` characters the oldest lines go first, then the oldest full entries, and the
    text says how many attempts it left out. The rule is fixed: the same entries give the same text.
    """
    judged = [e for e in entries if e.outcome not in (Outcome.DISCARDED, Outcome.APPROVED)]
    full = {id(e) for e in judged[-FULL_ENTRIES:]}
    blocks = [(id(e) in full, _full(e) if id(e) in full else _line(e)) for e in entries]
    left_out = 0
    while sum(len(text) + 1 for _, text in blocks) > DIARY_LIMIT and blocks:
        lines = [i for i, (is_full, _) in enumerate(blocks) if not is_full]
        del blocks[lines[0] if lines else 0]
        left_out += 1
    if not blocks:
        return ""
    head = [f"{left_out} earlier attempt(s) left out to keep this short."] if left_out else []
    return "\n".join([*head, *(text for _, text in blocks)])


def _cut(text: str, size: int) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= size else flat[: size - 3] + "..."


def _full(entry: Entry) -> str:
    lines = [f"### Attempt `{entry.attempt}`: {_verdict(entry)}"]
    if entry.said:
        lines.append(f"You said: {_cut(entry.said, SAID_CUT)}")
    if entry.detail:
        lines.append(f"Why: {entry.detail}")
    return "\n".join(lines) + "\n"


def _line(entry: Entry) -> str:
    why = f": {_cut(entry.detail, LINE_CUT)}" if entry.detail else ""
    return f"- `{entry.attempt}`: {_verdict(entry)}{why}"


def _verdict(entry: Entry) -> str:
    if entry.outcome is Outcome.DISCARDED:
        return "discarded (infrastructure)" if entry.infrastructure else "discarded"
    return {
        Outcome.REJECTED: "rejected",
        Outcome.APPROVED: "approved",
        Outcome.OPEN: "did not finish",
    }[entry.outcome]


def stage_diary(state: RunState, stage: str, current: str) -> str:
    """The text for ``current``, the attempt about to run: what the stage's earlier ones did."""
    return diary_text([e for e in stage_entries(state, stage) if e.attempt != current])
