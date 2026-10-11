"""How a run ends, as the process that started it reports it."""

from dataclasses import dataclass
from enum import IntEnum

from forja.core.states import ExecutionState


class ExitCode(IntEnum):
    DELIVERED = 0
    FAILED = 1
    INVALID_CONFIG = 2
    PAUSED = 3  # stopped safely with state saved; the next ``forja`` resumes
    NOTHING_INTEGRATED = 4  # delivered, but every task was blocked: the branch has no changes
    INTERRUPTED = 130  # the user asked to stop


@dataclass(frozen=True)
class Outcome:
    state: ExecutionState
    exit_code: ExitCode
    message: str


class StopRun(Exception):
    """Unwinds a task to the orchestrator, which pauses the run with this reason."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def exit_code_for(state: ExecutionState) -> ExitCode:
    """The code for the state a run was left in; any state in the middle means it was cut short."""
    match state:
        case ExecutionState.DELIVERED | ExecutionState.DISCARDED:
            return ExitCode.DELIVERED
        case ExecutionState.FAILED:
            return ExitCode.FAILED
        case ExecutionState.PAUSED:
            return ExitCode.PAUSED
    return ExitCode.INTERRUPTED
