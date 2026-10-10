"""Transition tables of contract 1, transcribed by hand from docs/Especificação.md.

Deliberately independent of ``src``: the tests compare the implementation against these
literals, so a typo in the implementation table cannot hide behind a copy of itself.
Names are the English values approved for the persisted state strings.
"""

from dataclasses import dataclass
from enum import StrEnum

from forja.core.states import (
    ATTEMPT_MACHINE,
    EXECUTION_MACHINE,
    STAGE_MACHINE,
    TASK_MACHINE,
    AttemptState,
    ExecutionState,
    StageState,
    StateMachine,
    TaskState,
)


@dataclass(frozen=True)
class LevelOracle:
    name: str
    initial: str
    explicit: dict[str, frozenset[str]]
    terminals: frozenset[str]
    # Resumable state -> states that are valid as ``previous`` when returning from it.
    resumable_previous: dict[str, frozenset[str]]


EXECUTION = LevelOracle(
    name="execution",
    initial="preparing",
    explicit={
        "preparing": frozenset({"confirmed", "discarded"}),
        "confirmed": frozenset({"measuring_baseline"}),
        "measuring_baseline": frozenset({"planning", "paused", "failed"}),
        "planning": frozenset({"executing", "failed"}),
        "executing": frozenset({"closing", "paused", "failed"}),
        "closing": frozenset({"delivered", "paused", "failed"}),
        "paused": frozenset({"failed"}),
        "failed": frozenset({"discarded"}),
        "delivered": frozenset(),
        "discarded": frozenset(),
    },
    terminals=frozenset({"delivered", "discarded"}),
    resumable_previous={
        "paused": frozenset({"measuring_baseline", "executing", "closing"}),
        "failed": frozenset({"measuring_baseline", "planning", "executing", "closing", "paused"}),
    },
)

TASK = LevelOracle(
    name="task",
    initial="pending",
    explicit={
        "pending": frozenset({"awaiting_dependency", "in_progress"}),
        "awaiting_dependency": frozenset({"pending", "cancelled"}),
        "in_progress": frozenset({"integrated", "blocked"}),
        "integrated": frozenset(),
        "blocked": frozenset(),
        "cancelled": frozenset(),
    },
    terminals=frozenset({"integrated", "blocked", "cancelled"}),
    resumable_previous={},
)

STAGE = LevelOracle(
    name="stage",
    initial="pending",
    explicit={
        "pending": frozenset({"in_progress"}),
        "in_progress": frozenset({"committed", "exhausted", "infra_paused"}),
        "infra_paused": frozenset({"in_progress"}),
        "committed": frozenset(),
        "exhausted": frozenset(),
    },
    terminals=frozenset({"committed", "exhausted"}),
    resumable_previous={},
)

ATTEMPT = LevelOracle(
    name="attempt",
    initial="created",
    explicit={
        "created": frozenset({"workcopy_ready"}),
        "workcopy_ready": frozenset({"agent_running"}),
        "agent_running": frozenset({"validating", "discarded"}),
        "validating": frozenset({"approved", "rejected", "discarded"}),
        "approved": frozenset({"committed"}),
        "rejected": frozenset(),
        "discarded": frozenset(),
        "committed": frozenset(),
    },
    terminals=frozenset({"rejected", "discarded", "committed"}),
    resumable_previous={},
)


@dataclass(frozen=True)
class LevelCase:
    oracle: LevelOracle
    state_type: type[StrEnum]
    machine: StateMachine  # type: ignore[type-arg]


CASES = [
    LevelCase(EXECUTION, ExecutionState, EXECUTION_MACHINE),
    LevelCase(TASK, TaskState, TASK_MACHINE),
    LevelCase(STAGE, StageState, STAGE_MACHINE),
    LevelCase(ATTEMPT, AttemptState, ATTEMPT_MACHINE),
]
