"""What the user confirmed, kept in the event that confirms the run so a resume finds it again."""

from dataclasses import dataclass

from pydantic import JsonValue, ValidationError

from forja.core.authorization import Grants
from forja.core.events.state import RunState
from forja.core.isolation import IsolationRecord
from forja.core.states import ExecutionState, Level


class ConfirmationError(Exception):
    """The run has no usable confirmation record."""


@dataclass(frozen=True)
class Confirmation:
    grants: Grants
    isolation: IsolationRecord


def confirmation_payload(confirmation: Confirmation) -> dict[str, JsonValue]:
    """Payload for the ``preparing -> confirmed`` transition."""
    return {
        "grants": confirmation.grants.model_dump(mode="json"),
        "isolation": confirmation.isolation.model_dump(mode="json"),
    }


def load_confirmation(state: RunState) -> Confirmation:
    """Read the grants and isolation levels back from the events of a run."""
    payload = (
        state.transition_payload(Level.EXECUTION, state.run_id, ExecutionState.CONFIRMED)
        if state.has_target(Level.EXECUTION, state.run_id)
        else None
    )
    if payload is None:
        raise ConfirmationError("the run was never confirmed")
    try:
        return Confirmation(
            Grants.model_validate(payload.get("grants")),
            IsolationRecord.model_validate(payload.get("isolation")),
        )
    except ValidationError as error:
        raise ConfirmationError(
            f"the confirmation record is invalid: {error.errors()[0]['msg']}"
        ) from None
