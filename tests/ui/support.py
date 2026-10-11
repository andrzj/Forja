"""Events made by hand, to drive a view without a run."""

from typing import Any

from forja.core.events import EffectEvent, IntentEvent, ProgressEvent, TransitionEvent
from forja.core.states import Level
from forja.ui.view import ViewModel

TIME = "2026-10-10T12:31:07.000000Z"
CHAIN: dict[str, Any] = {"prev": "0" * 64, "hash": "1" * 64}


class Sequence:
    """Numbers the events the way a log would."""

    def __init__(self) -> None:
        self.seq = 0

    def next(self) -> int:
        self.seq += 1
        return self.seq


NUMBERS = Sequence()


def transition(
    level: Level,
    target: str,
    to: str,
    *,
    payload: dict[str, Any] | None = None,
    frm: str | None = None,
) -> TransitionEvent:
    return TransitionEvent(
        **CHAIN, schema_version=1, seq=NUMBERS.next(), time=TIME, run_id="r1", level=level,
        target_id=target,
        type="transition", from_state=frm, to_state=to, payload=payload or {},
    )  # fmt: skip


def progress(kind: str, **payload: Any) -> ProgressEvent:
    return ProgressEvent(
        **CHAIN, schema_version=1, seq=NUMBERS.next(), time=TIME, run_id="r1",
        level=Level.EXECUTION, target_id="r1", type="progress", payload={"kind": kind, **payload},
    )  # fmt: skip


def activity(kind: str, **payload: Any) -> ProgressEvent:
    return progress("agent_activity", type=kind, **payload)


def tool(kind: str, operation_id: str, operation: str = "run_tool") -> IntentEvent | EffectEvent:
    common: dict[str, Any] = dict(
        **CHAIN, schema_version=1, seq=NUMBERS.next(), time=TIME, run_id="r1", level=Level.ATTEMPT,
        target_id="t1-a1", operation=operation, operation_id=operation_id, payload={},
    )  # fmt: skip
    return (
        IntentEvent(type="intent", **common)
        if kind == "intent"
        else EffectEvent(type="effect", **common)
    )


def model(**changes: Any) -> ViewModel:
    options: dict[str, Any] = dict(
        objective="refatorar", repo="meu-servico", branch="forja/r1", isolation="reduzido",
        token_limit=1000, attempts_max=3, clock=lambda: 100.0,
    )  # fmt: skip
    return ViewModel(**{**options, **changes})
