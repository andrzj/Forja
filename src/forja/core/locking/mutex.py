"""Serializes the git commands that write, because every worktree shares one `.git`."""

import asyncio
import weakref
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path

from forja.core.failures import TransientFailure
from forja.core.locking.directory import (
    DirectoryLockSettings,
    LockHeld,
    LockOwner,
    release,
    try_acquire,
)

GIT_MUTEX_NAME = "git.mutex"


class MutexTimeout(TransientFailure):
    """The git mutex stayed busy for the whole wait; the orchestrator retries or pauses."""

    def __init__(self, timeout: float) -> None:
        self.timeout = timeout
        super().__init__(f"the git mutex was still busy after {timeout:g} s")


class GitMutex:
    """One mutex per repository: an ``asyncio.Lock`` inside the process, a directory between them.

    It is not reentrant: taking it while holding it waits until the timeout. Hold it for one git
    command, never across a call to an agent. A holder that died is taken over like an abandoned
    repository lock.
    """

    def __init__(
        self,
        locks: Path,
        owner_factory: Callable[[], LockOwner] = LockOwner.current,
        *,
        settings: DirectoryLockSettings | None = None,
        poll_interval: float = 0.05,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._directory = locks / GIT_MUTEX_NAME
        self._owner_factory = owner_factory
        self._settings = settings
        self._poll = poll_interval
        self._sleep = sleep
        self._local: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Lock] = (
            weakref.WeakKeyDictionary()
        )

    def _local_lock(self) -> asyncio.Lock:
        loop = asyncio.get_running_loop()
        if loop not in self._local:
            self._local[loop] = asyncio.Lock()
        return self._local[loop]

    @asynccontextmanager
    async def hold(self, *, timeout: float) -> AsyncIterator[None]:
        """Wait up to ``timeout`` seconds for the mutex; raise ``MutexTimeout`` if it stays busy."""
        local = self._local_lock()
        owner = self._owner_factory()
        try:
            async with asyncio.timeout(timeout):
                await local.acquire()
                try:
                    await self._take_directory(owner)
                except BaseException:
                    local.release()
                    raise
        except TimeoutError:
            raise MutexTimeout(timeout) from None
        try:
            yield
        finally:
            try:
                release(self._directory, owner)
            finally:
                local.release()

    async def _take_directory(self, owner: LockOwner) -> None:
        while True:
            try:
                try_acquire(self._directory, owner, self._settings)
            except LockHeld:
                await self._sleep(self._poll)
            else:
                return
