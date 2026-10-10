"""`paused` and `failed` may return to the state before them; the caller supplies that state."""

import itertools

import pytest

from forja.core.states import EXECUTION_MACHINE, ExecutionState, InvalidTransition
from tests.core.states.oracle import CASES, EXECUTION, LevelCase

S = ExecutionState

RETURN_CASES = [
    pytest.param(origin, destination, previous, id=f"{origin}->{destination}|prev={previous}")
    for origin in EXECUTION.resumable_previous
    for destination, previous in itertools.product(EXECUTION.explicit, (None, *EXECUTION.explicit))
]


@pytest.mark.parametrize(("origin", "destination", "previous"), RETURN_CASES)
def test_return_is_allowed_only_to_the_given_previous_state_when_it_could_have_led_here(
    origin: str, destination: str, previous: str | None
) -> None:
    explicit = destination in EXECUTION.explicit[origin]
    valid_return = (
        previous is not None
        and destination == previous
        and previous in EXECUTION.resumable_previous[origin]
    )
    prev_state = None if previous is None else S(previous)

    if explicit or valid_return:
        EXECUTION_MACHINE.validate(S(origin), S(destination), previous=prev_state)
    else:
        with pytest.raises(InvalidTransition):
            EXECUTION_MACHINE.validate(S(origin), S(destination), previous=prev_state)


def test_return_without_a_previous_state_is_rejected() -> None:
    for origin in (S.PAUSED, S.FAILED):
        for destination in S:
            if destination not in EXECUTION.explicit[origin.value]:
                with pytest.raises(InvalidTransition):
                    EXECUTION_MACHINE.validate(origin, destination)


def test_failed_that_came_from_paused_returns_to_paused() -> None:
    assert EXECUTION_MACHINE.apply(S.FAILED, S.PAUSED, previous=S.PAUSED) == S.PAUSED


def test_paused_returns_to_the_state_it_was_paused_from() -> None:
    assert EXECUTION_MACHINE.apply(S.PAUSED, S.EXECUTING, previous=S.EXECUTING) == S.EXECUTING
    with pytest.raises(InvalidTransition):
        EXECUTION_MACHINE.validate(S.PAUSED, S.PLANNING, previous=S.PLANNING)


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.oracle.name)
def test_previous_state_changes_nothing_for_non_resumable_origins(case: LevelCase) -> None:
    for origin, expected in case.oracle.explicit.items():
        if origin in case.oracle.resumable_previous:
            continue
        for previous in case.state_type:
            allowed = case.machine.allowed(case.state_type(origin), previous)
            assert {s.value for s in allowed} == expected
