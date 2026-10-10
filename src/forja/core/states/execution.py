from enum import StrEnum

from forja.core.states.level import Level
from forja.core.states.machine import StateMachine


class ExecutionState(StrEnum):
    PREPARING = "preparing"
    CONFIRMED = "confirmed"
    MEASURING_BASELINE = "measuring_baseline"
    PLANNING = "planning"
    EXECUTING = "executing"
    CLOSING = "closing"
    PAUSED = "paused"
    FAILED = "failed"
    DELIVERED = "delivered"
    DISCARDED = "discarded"


_S = ExecutionState

# PAUSED and FAILED also return to the state before them; see StateMachine.
EXECUTION_MACHINE = StateMachine(
    Level.EXECUTION,
    ExecutionState,
    {
        _S.PREPARING: {_S.CONFIRMED, _S.DISCARDED},
        _S.CONFIRMED: {_S.MEASURING_BASELINE},
        _S.MEASURING_BASELINE: {_S.PLANNING, _S.PAUSED, _S.FAILED},
        _S.PLANNING: {_S.EXECUTING, _S.FAILED},
        _S.EXECUTING: {_S.CLOSING, _S.PAUSED, _S.FAILED},
        _S.CLOSING: {_S.DELIVERED, _S.PAUSED, _S.FAILED},
        _S.PAUSED: {_S.FAILED},
        _S.FAILED: {_S.DISCARDED},
        _S.DELIVERED: set(),
        _S.DISCARDED: set(),
    },
    initial=_S.PREPARING,
    resumable={_S.PAUSED, _S.FAILED},
)
