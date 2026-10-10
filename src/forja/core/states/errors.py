from enum import StrEnum

from forja.core.states.level import Level


class InvalidTransition(Exception):
    """Raised when a state change is not allowed by the transition table of its level."""

    def __init__(
        self,
        level: Level,
        origin: StrEnum,
        destination: StrEnum,
        previous: StrEnum | None = None,
    ) -> None:
        self.level = level
        self.origin = origin
        self.destination = destination
        self.previous = previous
        message = f"{level.value}: transition {origin.value} -> {destination.value} is not allowed"
        if previous is not None:
            message += f" (previous state given: {previous.value})"
        super().__init__(message)
