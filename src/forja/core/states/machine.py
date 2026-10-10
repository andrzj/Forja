from collections.abc import Iterable, Mapping
from enum import StrEnum
from types import MappingProxyType

from forja.core.states.errors import InvalidTransition
from forja.core.states.level import Level


class StateMachine[S: StrEnum]:
    """Pure transition graph for one level. It holds no current state and has no side effects.

    A state in ``resumable`` may also go back to the state the run was in before entering it.
    The machine cannot know that state, so the caller passes it as ``previous`` (the
    orchestrator reads it from the event log). Only states with an edge into the resumable
    state are valid as ``previous``.

    Guards that depend on other objects (for example, all stages committed before a task is
    integrated) are not checked here; they belong to the orchestrator.
    """

    def __init__(
        self,
        level: Level,
        state_type: type[S],
        table: Mapping[S, Iterable[S]],
        *,
        initial: S,
        resumable: Iterable[S] = (),
    ) -> None:
        missing = set(state_type) - set(table)
        if missing:
            names = sorted(state.value for state in missing)
            raise ValueError(f"{level.value}: states without a table row: {names}")
        self._level = level
        self._state_type = state_type
        self._initial = initial
        self._table: Mapping[S, frozenset[S]] = MappingProxyType(
            {state: frozenset(table[state]) for state in state_type}
        )
        self._resume_sources: Mapping[S, frozenset[S]] = MappingProxyType(
            {
                state: frozenset(
                    origin for origin, destinations in self._table.items() if state in destinations
                )
                for state in resumable
            }
        )
        empty = [state.value for state, sources in self._resume_sources.items() if not sources]
        if empty:
            raise ValueError(f"{level.value}: resumable states with no way in: {empty}")

    @property
    def level(self) -> Level:
        return self._level

    @property
    def state_type(self) -> type[S]:
        return self._state_type

    @property
    def initial(self) -> S:
        """The only state a new object of this level may start in."""
        return self._initial

    @property
    def table(self) -> Mapping[S, frozenset[S]]:
        """Read-only explicit transitions; the return to a previous state is not listed."""
        return self._table

    def is_resumable(self, state: S) -> bool:
        """Whether ``state`` can return to the state before it."""
        self._check_type(state)
        return state in self._resume_sources

    def is_terminal(self, state: S) -> bool:
        self._check_type(state)
        return not self._table[state] and state not in self._resume_sources

    def allowed(self, origin: S, previous: S | None = None) -> frozenset[S]:
        """Destinations reachable from ``origin``, including the return to ``previous``."""
        self._check_type(origin)
        if previous is not None:
            self._check_type(previous)
        destinations = self._table[origin]
        if previous is not None and previous in self._resume_sources.get(origin, frozenset()):
            return destinations | {previous}
        return destinations

    def validate(self, origin: S, destination: S, *, previous: S | None = None) -> None:
        """Raise ``InvalidTransition`` unless ``origin -> destination`` is allowed."""
        self._check_type(destination)
        if destination not in self.allowed(origin, previous):
            raise InvalidTransition(self._level, origin, destination, previous)

    def apply(self, origin: S, destination: S, *, previous: S | None = None) -> S:
        """Return ``destination`` if the transition is allowed; the machine itself never changes."""
        self.validate(origin, destination, previous=previous)
        return destination

    def _check_type(self, state: object) -> None:
        if not isinstance(state, self._state_type):
            raise TypeError(
                f"{self._level.value}: expected {self._state_type.__name__}, "
                f"got {type(state).__name__}"
            )
