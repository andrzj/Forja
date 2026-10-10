from dataclasses import dataclass
from enum import StrEnum


class Decision(StrEnum):
    """What the orchestrator must do about an operation whose intent has no recorded effect."""

    ALREADY_DONE = "already_done"  # record the effect; do not repeat
    REDO = "redo"  # not done (or only partly): run it again
    DISCARD_ATTEMPT = "discard_attempt"  # cannot be verified or repeated: drop the attempt


@dataclass(frozen=True)
class Reconciliation:
    """A verdict. Reconciling never changes run state; the orchestrator does that."""

    decision: Decision
    counts_as_infra_failure: bool = False


class ReconciliationError(Exception):
    """The facts needed to verify an operation are missing, so no verdict is possible."""
