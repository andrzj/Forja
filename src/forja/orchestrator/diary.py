"""The log book of a task: what each attempt said and how it ended, read from the log.

A projection of the run state, like the summary: nothing is written, so a resumed run, or a log cut
short, gives the same entries as a run that was never interrupted. The agent's own words are those
the cycle kept when it moved the attempt to validating; the outcome is the transition that ended it.
"""

import re
from collections import Counter
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


def diary_text(entries: list[Entry]) -> str:
    """The earlier attempts of a stage, as the agent is shown them; empty when there are none.

    Every attempt, in order, with what the agent said and why it ended as it did, whole: nothing
    is cut and no attempt is left out. The same entries give the same text.
    """
    return "\n".join(_full(e) for e in entries)


def _full(entry: Entry) -> str:
    lines = [f"### Attempt `{entry.attempt}`: {_verdict(entry)}"]
    if entry.said:
        lines.append(_quoted("You said", entry.said))
    if entry.detail:
        lines.append(_quoted("Why", entry.detail))
    return "\n".join(lines) + "\n"


def _quoted(label: str, text: str) -> str:
    """The words as they were. Several lines are quoted, so they cannot pass for structure."""
    lines = text.strip().splitlines()
    if len(lines) <= 1:
        return f"{label}: {text.strip()}"
    return f"{label}:\n" + "\n".join(f"> {line}" for line in lines)


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
    return diary_text(_earlier(state, stage, current))


# "Attack the Premise" of unclebob/ub-mode (SKILL.md), with "hypothesis" for "premise": the
# Forja already uses Assumption and PREMISE for something else.
HYPOTHESIS_REQUEST = (
    "When two fixes that share one hypothesis fail the same gate, write that hypothesis in one "
    "sentence and count which actors hold the imbalance.\n"
    "Remove the assignment.\n"
    "Do not start another fix until you have done that.\n\n"
    "Write the hypothesis in one sentence in the `reason` of your action."
)
REPEATS = 2  # rejections at the same gate that call for the hypothesis
_WHERE = re.compile(r"gate \S+ \([^)]*\)")


def hypothesis_request(entries: list[Entry]) -> str:
    """The request to state the hypothesis, when two attempts were rejected at the same gate.

    A discard for infrastructure is not a rejection by a gate and does not count. Empty otherwise.
    """
    gates = Counter(
        found.group()
        for e in entries
        if e.outcome is Outcome.REJECTED and (found := _WHERE.match(e.detail))
    )
    return HYPOTHESIS_REQUEST if any(n >= REPEATS for n in gates.values()) else ""


def stage_last_said(state: RunState, stage: str, current: str) -> str:
    """What the agent said in the last rejected attempt of the stage, before ``current``."""
    rejected = [e for e in _earlier(state, stage, current) if e.outcome is Outcome.REJECTED]
    return rejected[-1].said if rejected else ""


def stage_hypothesis(state: RunState, stage: str, current: str) -> str:
    return hypothesis_request(_earlier(state, stage, current))


_RECORD_VERDICTS = {
    Outcome.REJECTED: "rejeitada",
    Outcome.APPROVED: "aprovada",
    Outcome.DISCARDED: "descartada",
    Outcome.OPEN: "não terminou",
}
_RECORD_DECISIONS = {EXHAUSTED: "etapa esgotada", BLOCKED: "tarefa bloqueada"}


def task_diary(state: RunState, task: str, current: str) -> str:
    """The log book of a task as the Forja commits it beside the change record, in Markdown.

    Every attempt of every stage of the task except ``current``, the one being judged, with what the
    agent said and the reason of the rejection as they were kept, quoted and not cut here (the cycle
    already limited both), then what the Forja decided. Built from the log only, so a resumed run
    writes the same text.
    """
    entries = [e for e in task_entries(state, task) if e.attempt != current]
    decisions = task_decisions(state, task)
    lines = [f"# Diário de bordo: {task}", ""]
    if not entries and not decisions:
        return "\n".join([*lines, "Nenhuma tentativa anterior.", ""])
    for entry in entries:
        verdict = _RECORD_VERDICTS[entry.outcome]
        if entry.infrastructure:
            verdict += " (infraestrutura)"
        lines += [f"## Tentativa `{entry.attempt}` da etapa `{entry.stage}`: {verdict}", ""]
        if entry.said:
            lines += _record_quote("Disse", entry.said)
        if entry.detail:
            lines += _record_quote(
                "Gates aprovados" if entry.outcome is Outcome.APPROVED else "Motivo", entry.detail
            )
    for decision in decisions:
        lines += [
            f"## Decisão da Forja: {_RECORD_DECISIONS[decision.what]} `{decision.target}`",
            "",
        ]
        if decision.reason:
            lines += _record_quote("Motivo", decision.reason)
    return "\n".join(lines)


def _record_quote(label: str, text: str) -> list[str]:
    return [f"{label}:", "", *(f"> {line}".rstrip() for line in text.strip().splitlines()), ""]


def _earlier(state: RunState, stage: str, current: str) -> list[Entry]:
    return [e for e in stage_entries(state, stage) if e.attempt != current]
