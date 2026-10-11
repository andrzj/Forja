"""Structural guards: table completeness, reachability, immutability, type safety, error content."""

from collections import deque
from enum import StrEnum

import pytest

from forja.core.states import (
    EXECUTION_MACHINE,
    TASK_MACHINE,
    ExecutionState,
    InvalidTransition,
    Level,
    StateMachine,
    TaskState,
)
from tests.core.states.oracle import CASES, LevelCase, LevelOracle


def _graph(oracle: LevelOracle) -> dict[str, set[str]]:
    graph = {state: set(dests) for state, dests in oracle.explicit.items()}
    for resumable, sources in oracle.resumable_previous.items():
        graph[resumable] |= sources
    return graph


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.oracle.name)
def test_enum_values_are_exactly_the_spec_states(case: LevelCase) -> None:
    assert {s.value for s in case.state_type} == set(case.oracle.explicit)


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.oracle.name)
def test_initial_state_matches_the_spec(case: LevelCase) -> None:
    assert case.machine.initial.value == case.oracle.initial


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.oracle.name)
def test_resumable_states_match_the_spec(case: LevelCase) -> None:
    actual = {s.value for s in case.state_type if case.machine.is_resumable(s)}
    assert actual == set(case.oracle.resumable_previous)


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.oracle.name)
def test_every_state_is_reachable_from_the_initial_state(case: LevelCase) -> None:
    graph = _graph(case.oracle)
    seen = {case.oracle.initial}
    queue = deque(seen)
    while queue:
        for nxt in graph[queue.popleft()] - seen:
            seen.add(nxt)
            queue.append(nxt)
    assert seen == set(graph)


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.oracle.name)
def test_every_state_can_reach_a_terminal_state(case: LevelCase) -> None:
    graph = _graph(case.oracle)
    for start in graph:
        seen = {start}
        queue = deque(seen)
        while queue:
            for nxt in graph[queue.popleft()] - seen:
                seen.add(nxt)
                queue.append(nxt)
        assert seen & case.oracle.terminals, start


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.oracle.name)
def test_table_is_read_only(case: LevelCase) -> None:
    some_state = next(iter(case.state_type))
    with pytest.raises(TypeError):
        case.machine.table[some_state] = frozenset()  # type: ignore[index]
    row = case.machine.table[some_state]
    assert isinstance(row, frozenset)


def test_rejected_transition_leaves_the_machine_unchanged() -> None:
    before = dict(EXECUTION_MACHINE.table)
    with pytest.raises(InvalidTransition):
        EXECUTION_MACHINE.apply(ExecutionState.PREPARING, ExecutionState.DELIVERED)
    assert dict(EXECUTION_MACHINE.table) == before


def test_error_carries_level_origin_destination_and_previous() -> None:
    with pytest.raises(InvalidTransition) as info:
        EXECUTION_MACHINE.validate(
            ExecutionState.PAUSED, ExecutionState.PLANNING, previous=ExecutionState.EXECUTING
        )
    error = info.value
    assert error.level is Level.EXECUTION
    assert error.origin is ExecutionState.PAUSED
    assert error.destination is ExecutionState.PLANNING
    assert error.previous is ExecutionState.EXECUTING
    assert "paused -> planning" in str(error)


def test_state_of_another_level_is_rejected() -> None:
    with pytest.raises(TypeError):
        EXECUTION_MACHINE.validate(TaskState.PENDING, ExecutionState.CONFIRMED)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        EXECUTION_MACHINE.validate(ExecutionState.PREPARING, TaskState.PENDING)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        TASK_MACHINE.allowed(TaskState.PENDING, previous=ExecutionState.PAUSED)  # type: ignore[arg-type]


def test_plain_string_is_not_a_state() -> None:
    with pytest.raises(TypeError):
        EXECUTION_MACHINE.validate("preparing", "confirmed")  # type: ignore[arg-type]


class _Tiny(StrEnum):
    A = "a"
    B = "b"


def test_machine_refuses_a_table_that_misses_a_state() -> None:
    with pytest.raises(ValueError, match="without a table row"):
        StateMachine(Level.TASK, _Tiny, {_Tiny.A: {_Tiny.B}}, initial=_Tiny.A)


def test_machine_refuses_a_resumable_state_with_no_way_in() -> None:
    with pytest.raises(ValueError, match="no way in"):
        StateMachine(
            Level.TASK,
            _Tiny,
            {_Tiny.A: set(), _Tiny.B: set()},
            initial=_Tiny.A,
            resumable={_Tiny.B},
        )


def test_a_machine_exposes_what_it_was_built_with() -> None:
    # Built here, not at import: a fault in the constructor must show up in a test run.
    machine = StateMachine(
        Level.STAGE, _Tiny, {_Tiny.A: {_Tiny.B}, _Tiny.B: set()}, initial=_Tiny.B
    )

    assert machine.level is Level.STAGE
    assert machine.state_type is _Tiny
    assert machine.initial is _Tiny.B


def test_the_error_for_a_state_of_another_level_names_both_types() -> None:
    with pytest.raises(TypeError) as info:
        EXECUTION_MACHINE.validate(TaskState.PENDING, ExecutionState.CONFIRMED)  # type: ignore[arg-type]

    assert str(info.value) == "execution: expected ExecutionState, got TaskState"


def test_the_error_for_a_table_with_missing_rows_lists_them_sorted() -> None:
    with pytest.raises(ValueError) as info:
        StateMachine(Level.TASK, _Tiny, {}, initial=_Tiny.A)

    assert str(info.value) == "task: states without a table row: ['a', 'b']"


def test_the_error_for_a_resumable_state_with_no_way_in_lists_it() -> None:
    with pytest.raises(ValueError) as info:
        StateMachine(
            Level.TASK,
            _Tiny,
            {_Tiny.A: set(), _Tiny.B: set()},
            initial=_Tiny.A,
            resumable={_Tiny.B},
        )

    assert str(info.value) == "task: resumable states with no way in: ['b']"
