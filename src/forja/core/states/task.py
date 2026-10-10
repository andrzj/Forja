from enum import StrEnum

from forja.core.states.level import Level
from forja.core.states.machine import StateMachine


class TaskState(StrEnum):
    PENDING = "pending"
    AWAITING_DEPENDENCY = "awaiting_dependency"
    IN_PROGRESS = "in_progress"
    INTEGRATED = "integrated"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"


_S = TaskState

TASK_MACHINE = StateMachine(
    Level.TASK,
    TaskState,
    {
        _S.PENDING: {_S.AWAITING_DEPENDENCY, _S.IN_PROGRESS},
        _S.AWAITING_DEPENDENCY: {_S.PENDING, _S.CANCELLED},
        _S.IN_PROGRESS: {_S.INTEGRATED, _S.BLOCKED},
        _S.INTEGRATED: set(),
        _S.BLOCKED: set(),
        _S.CANCELLED: set(),
    },
    initial=_S.PENDING,
)
