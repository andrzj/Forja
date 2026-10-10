from enum import StrEnum

from forja.core.states.level import Level
from forja.core.states.machine import StateMachine


class StageState(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    INFRA_PAUSED = "infra_paused"
    COMMITTED = "committed"
    EXHAUSTED = "exhausted"


_S = StageState

STAGE_MACHINE = StateMachine(
    Level.STAGE,
    StageState,
    {
        _S.PENDING: {_S.IN_PROGRESS},
        _S.IN_PROGRESS: {_S.COMMITTED, _S.EXHAUSTED, _S.INFRA_PAUSED},
        _S.INFRA_PAUSED: {_S.IN_PROGRESS},
        _S.COMMITTED: set(),
        _S.EXHAUSTED: set(),
    },
    initial=_S.PENDING,
)
