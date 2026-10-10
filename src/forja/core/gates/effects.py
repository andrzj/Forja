from dataclasses import dataclass

from forja.core.gates.models import (
    Approved,
    Effect,
    GateResult,
    Inconclusive,
    InconclusivePolicy,
    Mode,
    NotApplicable,
    Rejected,
)

# Effects that end the check sequence: nothing after them runs.
STOPPING_EFFECTS = frozenset({Effect.REJECT_ATTEMPT, Effect.BLOCK_TASK})


class InvalidCheckSettings(ValueError):
    pass


@dataclass(frozen=True)
class CheckSettings:
    """Mode and inconclusive policy of one check.

    A blocking check must say what happens when its measurement cannot be made; there is no
    default, so the choice is always deliberate. An observation check may carry the policy ready
    for the day it is promoted.
    """

    mode: Mode
    on_inconclusive: InconclusivePolicy | None = None

    def __post_init__(self) -> None:
        if self.mode is Mode.BLOCKING and self.on_inconclusive is None:
            raise InvalidCheckSettings("a blocking check needs an on_inconclusive policy")


def decide_effect(settings: CheckSettings, result: GateResult) -> Effect:
    """The single place that combines mode, policy and result."""
    match result:
        case Approved() | NotApplicable():
            return Effect.PASS
        case Rejected() | Inconclusive() if settings.mode is Mode.OBSERVATION:
            return Effect.REPORT_ONLY
        case Rejected():
            return Effect.REJECT_ATTEMPT
        case Inconclusive():
            if settings.on_inconclusive is InconclusivePolicy.BLOCK:
                return Effect.BLOCK_TASK
            return Effect.CONTINUE_WITH_ASSUMPTION
    raise AssertionError(f"unhandled result {result!r}")  # pragma: no cover
