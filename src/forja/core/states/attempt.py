from enum import StrEnum

from forja.core.states.level import Level
from forja.core.states.machine import StateMachine


class AttemptState(StrEnum):
    CREATED = "created"
    WORKCOPY_READY = "workcopy_ready"
    AGENT_RUNNING = "agent_running"
    VALIDATING = "validating"
    APPROVED = "approved"
    REJECTED = "rejected"
    DISCARDED = "discarded"
    COMMITTED = "committed"


_S = AttemptState

ATTEMPT_MACHINE = StateMachine(
    Level.ATTEMPT,
    AttemptState,
    {
        _S.CREATED: {_S.WORKCOPY_READY},
        _S.WORKCOPY_READY: {_S.AGENT_RUNNING},
        _S.AGENT_RUNNING: {_S.VALIDATING, _S.DISCARDED},
        _S.VALIDATING: {_S.APPROVED, _S.REJECTED, _S.DISCARDED},
        _S.APPROVED: {_S.COMMITTED},
        _S.REJECTED: set(),
        _S.DISCARDED: set(),
        _S.COMMITTED: set(),
    },
    initial=_S.CREATED,
)
