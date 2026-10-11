"""Finding a run that was left unfinished in this repository, and deciding what to do with it.

Running ``forja`` after a stop, a crash or a blocking error finds the incomplete run and asks only
one thing: resume or discard. Discarding is careful: the run is marked discarded and the commands
to remove its branches are shown, but the Forja does not delete branches on its own.
"""

import os
from dataclasses import dataclass
from pathlib import Path

from forja.core.events.versioning import BadLine, parse_line
from forja.core.states import ExecutionState, Level

OPEN_STATES = frozenset(
    {
        ExecutionState.PREPARING,
        ExecutionState.CONFIRMED,
        ExecutionState.MEASURING_BASELINE,
        ExecutionState.PLANNING,
        ExecutionState.EXECUTING,
        ExecutionState.CLOSING,
        ExecutionState.PAUSED,
    }
)


@dataclass(frozen=True)
class Unfinished:
    run_id: str
    state: str
    reason: str
    directory: Path


def _same(a: str, b: Path) -> bool:
    return os.path.normcase(os.path.realpath(a)) == os.path.normcase(os.path.realpath(b))


def read_run(directory: Path) -> tuple[str, str, str] | None:
    """``(repo, state, reason)`` of a run from its log, or ``None`` if it was never confirmed."""
    log = directory / "events.jsonl"
    if not log.exists():
        return None
    repo, state, reason = "", "", ""
    for raw in [line for line in log.read_bytes().split(b"\n") if line]:
        try:
            event = parse_line(raw)
        except BadLine:
            break
        if event.type == "transition" and event.level is Level.EXECUTION:
            state, reason = event.to_state, str(event.payload.get("reason", ""))
            config = event.payload.get("config")
            if event.to_state == ExecutionState.CONFIRMED.value and isinstance(config, dict):
                repo = str(config.get("repo", ""))
    return (repo, state, reason) if repo else None


def find_unfinished(home: Path, repo: Path) -> list[Unfinished]:
    """The runs of ``repo`` that can still be resumed, the newest first."""
    runs = home / "runs"
    if not runs.is_dir():
        return []
    found = []
    for directory in sorted(runs.iterdir(), key=lambda item: item.stat().st_mtime, reverse=True):
        info = read_run(directory)
        if info and _same(info[0], repo) and info[1] in {s.value for s in OPEN_STATES}:
            found.append(Unfinished(directory.name, info[1], info[2], directory))
    return found


def discard(directory: Path) -> None:
    """Mark a run as discarded, going through the failed state the machine requires.

    Nothing is deleted: the branches and the log stay, and ``removal_commands`` tells the person
    how to remove the branches themselves.
    """
    from forja.core.events import EventLog  # noqa: PLC0415

    log = EventLog.open(directory / "events.jsonl", directory.name)
    try:
        state = log.state.state_of(Level.EXECUTION, directory.name)
        assert isinstance(state, ExecutionState)
        reason = {"reason": "discarded_by_user"}
        if state is ExecutionState.CONFIRMED:
            log.append_transition(
                Level.EXECUTION, directory.name, state, ExecutionState.MEASURING_BASELINE
            )
            state = ExecutionState.MEASURING_BASELINE
        if state is not ExecutionState.FAILED:
            log.append_transition(
                Level.EXECUTION, directory.name, state, ExecutionState.FAILED, payload=reason
            )
        log.append_transition(
            Level.EXECUTION,
            directory.name,
            ExecutionState.FAILED,
            ExecutionState.DISCARDED,
            payload=reason,
        )
    finally:
        log.close()


def removal_commands(run_id: str) -> list[str]:
    return [
        "git worktree prune",
        f'git branch --list "forja-run/{run_id}" "forja/{run_id}/*"',
        f'git branch -D "forja-run/{run_id}"   # e as branches forja/{run_id}/…, se existirem',
    ]
