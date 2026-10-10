"""One Forja session per repository (contract 3 resilience: exclusivity and resume)."""

import asyncio
import hashlib
import os
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import Self

from forja.core.failures import TransientFailure
from forja.core.idempotency.git import Git
from forja.core.locking.directory import (
    DirectoryLockSettings,
    LockHeld,
    LockOwner,
    TakenOver,
    release,
    try_acquire,
)

RUN_LOCK_NAME = "run.lock"


async def repository_id(git: Git) -> str:
    """Stable id of the repository behind ``git``, shared by all its worktrees.

    16 hex characters of the SHA-256 of the real, case-normalized path of the common git
    directory, so links, junctions and different spellings of the path give the same id.
    """
    (common,) = await git.lines("rev-parse", "--git-common-dir")
    resolved = (git.repo / common).resolve()
    return hashlib.sha256(os.path.normcase(str(resolved)).encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class LockPolicy:
    """What to do when another session holds the repository. Always chosen by the caller.

    ``refuse`` fails at once and tells who holds it, for an interactive preparation. ``wait``
    keeps trying until the holder finishes or dies, for unattended runs; the limit is mandatory.
    """

    wait: bool
    timeout: float | None = None
    poll_interval: float = 1.0

    @classmethod
    def refuse(cls) -> "LockPolicy":
        return cls(wait=False)

    @classmethod
    def wait_for(cls, timeout: float, poll_interval: float = 1.0) -> "LockPolicy":
        if timeout <= 0 or poll_interval <= 0:
            raise ValueError("the wait limit and the poll interval must be positive")
        return cls(wait=True, timeout=timeout, poll_interval=poll_interval)


class RepositoryBusy(Exception):
    """Another session holds the repository and the policy was to refuse."""

    def __init__(self, owner: LockOwner | None, reason: str) -> None:
        self.owner = owner
        self.reason = reason
        who = "" if owner is None else f" (pid {owner.pid} on {owner.machine}, run {owner.run_id})"
        super().__init__(f"another Forja session holds this repository{who}: {reason}")


class LockWaitTimeout(TransientFailure):
    """The repository stayed busy for the whole wait. Nothing was started; try again later."""

    def __init__(self, owner: LockOwner | None, waited: float) -> None:
        self.owner = owner
        self.waited = waited
        super().__init__(f"the repository was still busy after {waited:.1f} s")


class HeldLock:
    """The repository lock of this session. Release it when the run ends, or use ``with``."""

    def __init__(self, directory: Path, owner: LockOwner, taken_over: TakenOver | None) -> None:
        self.directory = directory
        self.owner = owner
        self.taken_over = taken_over  # set when an abandoned lock was taken over

    def release(self) -> bool:
        return release(self.directory, self.owner)

    def still_ours(self) -> bool:
        from forja.core.locking.directory import _read_owner

        current = _read_owner(self.directory)
        return current is not None and current.nonce == self.owner.nonce

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.release()


async def acquire_repository_lock(
    locks: Path,
    owner: LockOwner,
    policy: LockPolicy,
    *,
    settings: DirectoryLockSettings | None = None,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> HeldLock:
    """Take the lock of the repository whose lock directory is ``locks`` (``locks_dir(id)``)."""
    directory = locks / RUN_LOCK_NAME
    started = clock()
    while True:
        try:
            acquired = try_acquire(directory, owner, settings)
        except LockHeld as held:
            if not policy.wait:
                raise RepositoryBusy(held.owner, held.reason) from None
            waited = clock() - started
            assert policy.timeout is not None
            if waited >= policy.timeout:
                raise LockWaitTimeout(held.owner, waited) from None
            await sleep(min(policy.poll_interval, policy.timeout - waited))
        else:
            return HeldLock(directory, owner, acquired.taken_over)
