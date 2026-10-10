"""A lock made of a directory, safe to take over when its owner died.

``mkdir`` either creates the directory or fails, atomically, on every file system Forja runs on.
The owner writes ``owner.json`` inside it: pid, machine, start time and the creation time of the
process, which tells a living owner from a different process that reused the pid.

Taking over an abandoned lock is the dangerous part: two processes may both see it dead, and a
live process may take it between one's look and one's move. Takeovers therefore go through a
short-lived guard directory; whoever holds the guard re-judges the lock and moves it aside by
renaming it, which only one process can do.
"""

import json
import os
import platform
import shutil
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError

from forja.core.artifacts.models import NonEmpty
from forja.core.atomic import atomic_write_bytes
from forja.core.events.models import Timestamp, canonical_json, format_time
from forja.core.process import creation_token

OWNER_FILE = "owner.json"
_MAX_ATTEMPTS = 50


class LockOwner(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    pid: int
    machine: NonEmpty
    started_at: Timestamp
    creation_token: int | None
    run_id: NonEmpty | None = None
    nonce: NonEmpty

    @classmethod
    def current(
        cls,
        run_id: str | None = None,
        *,
        machine: str | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> "LockOwner":
        """The calling process as a lock owner."""
        pid = os.getpid()
        return cls(
            pid=pid,
            machine=machine or platform.node() or "unknown",
            started_at=format_time(clock()),
            creation_token=creation_token(pid),
            run_id=run_id,
            nonce=uuid.uuid4().hex,
        )


def owner_is_alive(owner: LockOwner) -> bool:
    """The recorded process is still running and is the same process, not a reused pid."""
    token = creation_token(owner.pid)
    if token is None:
        return False
    return owner.creation_token is None or token == owner.creation_token


@dataclass(frozen=True)
class DirectoryLockSettings:
    """Time and liveness sources, replaceable in tests."""

    grace: float = 5.0  # a lock directory with no owner record is "being acquired" this long
    guard_ttl: float = 30.0  # a takeover guard older than this was abandoned
    machine: str = field(default_factory=lambda: platform.node() or "unknown")
    now: Callable[[], float] = time.time
    sleep: Callable[[float], None] = time.sleep
    is_alive: Callable[[LockOwner], bool] = owner_is_alive


class LockHeld(Exception):
    """The lock belongs to a live owner (or one that cannot be proven dead)."""

    def __init__(self, directory: Path, owner: LockOwner | None, reason: str) -> None:
        self.directory = directory
        self.owner = owner
        self.reason = reason
        super().__init__(f"{directory.name}: {reason}")


@dataclass(frozen=True)
class TakenOver:
    """What was found when an abandoned lock was taken over, for the record."""

    previous: LockOwner | None
    reason: str


@dataclass(frozen=True)
class Acquired:
    directory: Path
    owner: LockOwner
    taken_over: TakenOver | None


@dataclass(frozen=True)
class _Alive:
    owner: LockOwner | None
    reason: str


@dataclass(frozen=True)
class _Orphan:
    previous: LockOwner | None
    reason: str


class _Gone:
    """The directory vanished while it was being judged."""


def _read_owner(directory: Path) -> LockOwner | None:
    try:
        return LockOwner.model_validate(json.loads((directory / OWNER_FILE).read_bytes()))
    except (OSError, ValueError, ValidationError):
        return None


def _judge(directory: Path, settings: DirectoryLockSettings) -> _Alive | _Orphan | _Gone:
    owner = _read_owner(directory)
    if owner is None:
        try:
            age = settings.now() - directory.stat().st_mtime
        except FileNotFoundError:
            return _Gone()
        if age < settings.grace:
            return _Alive(None, "the lock is being acquired by another process")
        return _Orphan(None, "the lock has no valid owner record")
    if owner.machine != settings.machine:
        return _Alive(owner, f"held by another machine ({owner.machine})")
    if settings.is_alive(owner):
        return _Alive(owner, "held by a running process")
    return _Orphan(owner, "the owning process is gone")


def _stale_name(directory: Path) -> Path:
    return directory.with_name(f"{directory.name}.stale-{uuid.uuid4().hex[:8]}")


def _take_over(directory: Path, settings: DirectoryLockSettings) -> TakenOver | None | _Alive:
    """Move an abandoned lock aside. ``None`` means: look again, something changed."""
    guard = directory.with_name(directory.name + ".takeover")
    try:
        os.mkdir(guard)
    except FileExistsError:
        try:
            if settings.now() - guard.stat().st_mtime > settings.guard_ttl:
                shutil.rmtree(guard, ignore_errors=True)
        except FileNotFoundError:
            pass
        return None
    try:
        verdict = _judge(directory, settings)  # judged again, now that nobody else can move it
        if isinstance(verdict, _Alive):
            return verdict
        if not isinstance(verdict, _Orphan):
            return None
        stale = _stale_name(directory)
        try:
            os.rename(directory, stale)
        except (FileNotFoundError, PermissionError):
            return None
        shutil.rmtree(stale, ignore_errors=True)
        return TakenOver(verdict.previous, verdict.reason)
    finally:
        shutil.rmtree(guard, ignore_errors=True)


def try_acquire(
    directory: Path,
    owner: LockOwner,
    settings: DirectoryLockSettings | None = None,
) -> Acquired:
    """Take the lock once, or raise ``LockHeld``. Never waits for a live owner."""
    s = settings or DirectoryLockSettings()
    directory.parent.mkdir(parents=True, exist_ok=True)
    taken: TakenOver | None = None
    for _ in range(_MAX_ATTEMPTS):
        try:
            os.mkdir(directory)
        except FileExistsError:
            verdict = _judge(directory, s)
            if isinstance(verdict, _Alive):
                raise LockHeld(directory, verdict.owner, verdict.reason) from None
            if isinstance(verdict, _Orphan):
                outcome = _take_over(directory, s)
                if isinstance(outcome, _Alive):
                    raise LockHeld(directory, outcome.owner, outcome.reason) from None
                if outcome is not None:
                    taken = outcome
            s.sleep(0.01)
            continue
        try:
            atomic_write_bytes(
                directory / OWNER_FILE, canonical_json(owner.model_dump(mode="json"))
            )
        except BaseException:
            shutil.rmtree(directory, ignore_errors=True)
            raise
        return Acquired(directory, owner, taken)
    raise LockHeld(directory, None, "could not settle a race for the lock")


def release(directory: Path, owner: LockOwner) -> bool:
    """Give the lock back if it is still ours; returns whether it was.

    The directory is renamed first, so nobody ever sees a half-deleted lock.
    """
    current = _read_owner(directory)
    if current is None or current.nonce != owner.nonce:
        return False
    stale = _stale_name(directory)
    try:
        os.rename(directory, stale)
    except FileNotFoundError:
        return False
    shutil.rmtree(stale, ignore_errors=True)
    return True
