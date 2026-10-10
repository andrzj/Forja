import pytest

from forja.core.states import InvalidTransition
from tests.core.states.oracle import CASES, LevelCase


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.oracle.name)
def test_terminal_states_match_the_spec(case: LevelCase) -> None:
    actual = {s.value for s in case.state_type if case.machine.is_terminal(s)}
    assert actual == case.oracle.terminals


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.oracle.name)
def test_nothing_leaves_a_terminal_state_even_with_a_previous_state(case: LevelCase) -> None:
    for terminal in case.oracle.terminals:
        origin = case.state_type(terminal)
        assert case.machine.allowed(origin) == frozenset()
        for destination in case.state_type:
            for previous in (None, *case.state_type):
                with pytest.raises(InvalidTransition):
                    case.machine.validate(origin, destination, previous=previous)
