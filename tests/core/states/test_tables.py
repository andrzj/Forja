"""Exhaustive check: every (origin, destination) pair of every level against the spec oracle."""

import itertools
from enum import StrEnum

import pytest

from forja.core.states import InvalidTransition
from tests.core.states.oracle import CASES, LevelCase

PAIRS = [
    pytest.param(case, origin, destination, id=f"{case.oracle.name}:{origin}->{destination}")
    for case in CASES
    for origin, destination in itertools.product(case.oracle.explicit, repeat=2)
]


@pytest.mark.parametrize(("case", "origin", "destination"), PAIRS)
def test_pair_is_allowed_only_if_the_spec_allows_it(
    case: LevelCase, origin: str, destination: str
) -> None:
    origin_state = case.state_type(origin)
    destination_state = case.state_type(destination)

    if destination in case.oracle.explicit[origin]:
        assert case.machine.apply(origin_state, destination_state) == destination_state
    else:
        with pytest.raises(InvalidTransition):
            case.machine.validate(origin_state, destination_state)
        with pytest.raises(InvalidTransition):
            case.machine.apply(origin_state, destination_state)


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.oracle.name)
def test_allowed_set_equals_the_spec_row(case: LevelCase) -> None:
    for origin, expected in case.oracle.explicit.items():
        state = case.state_type(origin)
        allowed: frozenset[StrEnum] = case.machine.allowed(state)
        assert {s.value for s in allowed} == expected, origin


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.oracle.name)
def test_staying_in_the_same_state_is_never_a_transition(case: LevelCase) -> None:
    for state in case.state_type:
        with pytest.raises(InvalidTransition):
            case.machine.validate(state, state)
        for previous in case.state_type:
            with pytest.raises(InvalidTransition):
                case.machine.validate(state, state, previous=previous)
