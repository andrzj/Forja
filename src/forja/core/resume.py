"""Resuming an interrupted run: settle every operation the log left open.

The log is the only memory. An intent with no effect means the run stopped inside that operation.
Resuming ends the leftover process, asks the reconciler what became of the operation, and records
the answer so the log holds no open operation before the run goes on.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from forja.core.events import EventLog, OpenOperation
from forja.core.idempotency import Decision, Reconciliation
from forja.core.process import ProcessIdentity, kill_leftover
from forja.core.states import AttemptState, Level

# Looks at the world and says what became of one open operation; it never changes anything.
Reconciler = Callable[[OpenOperation], Awaitable[Reconciliation]]

DISCARD_REASON = "interrupted_operation"


class ResumeError(Exception):
    """The log cannot be settled by the rules of the idempotency table."""


@dataclass(frozen=True)
class ResumeAction:
    operation: OpenOperation
    reconciliation: Reconciliation


@dataclass(frozen=True)
class ResumePlan:
    """What resuming did, in the order it did it."""

    actions: tuple[ResumeAction, ...]
    killed: tuple[ProcessIdentity, ...]


async def resume(log: EventLog, reconcile: Reconciler) -> ResumePlan:
    """Settle every open operation of ``log`` and return what was decided.

    Each operation ends with an effect whose payload says how it was settled: ``reconciled`` is
    ``already_done`` (it happened), ``redo`` (it did not; the caller repeats it under a new
    operation id) or ``discard_attempt`` (it cannot be told or repeated; the attempt is dropped
    and counts as an infrastructure failure). Repeating this after an interruption is safe.
    """
    state = log.state
    killed = tuple(process for process in state.leftover_processes() if kill_leftover(process))
    actions: list[ResumeAction] = []
    for operation in sorted(state.open_operations.values(), key=lambda op: op.intent_seq):
        verdict = await reconcile(operation)
        if verdict.decision is Decision.DISCARD_ATTEMPT:
            _discard_attempt(log, operation)
        log.append_effect(
            operation.level,
            operation.target_id,
            operation.operation,
            operation.operation_id,
            payload={
                "reconciled": verdict.decision.value,
                "infra_failure": verdict.counts_as_infra_failure,
            },
        )
        actions.append(ResumeAction(operation, verdict))
    return ResumePlan(tuple(actions), killed)


def _discard_attempt(log: EventLog, operation: OpenOperation) -> None:
    if operation.level is not Level.ATTEMPT:
        raise ResumeError(f"{operation.operation} is on a {operation.level.value}, not an attempt")
    current = log.state.state_of(Level.ATTEMPT, operation.target_id)
    if current is AttemptState.DISCARDED:
        return  # an earlier resume got this far before it was interrupted
    log.append_transition(
        Level.ATTEMPT,
        operation.target_id,
        current,
        AttemptState.DISCARDED,
        payload={
            "reason": DISCARD_REASON,
            "operation": operation.operation,
            "infra_failure": True,
        },
    )
