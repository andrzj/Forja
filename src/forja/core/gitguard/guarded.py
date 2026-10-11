from collections.abc import Mapping
from pathlib import Path

from forja.core.authorization.branches import ProtectedBranches
from forja.core.gitguard.rules import HEAD_WRITERS, GitCommandRefused, check, writes
from forja.core.idempotency.git import Git, GitResult
from forja.core.locking.mutex import GitMutex


class GuardedGit(Git):
    """`Git` that refuses everything Forja must never do, before running it.

    Three kinds of rules apply. The words of the command are checked against an allow-list (see
    ``rules``). Commands that write to the branch HEAD is on are refused when that branch is
    protected. And rewriting the history of a branch whose tip is already on a remote is refused;
    a detached HEAD, as in a disposable attempt worktree, rewrites no named history.
    """

    def __init__(
        self,
        repo: Path,
        *,
        executable: str,
        env: Mapping[str, str],
        timeout: float,
        log_dir: Path,
        protected: ProtectedBranches,
        mutex: GitMutex | None = None,
        mutex_timeout: float | None = None,
    ) -> None:
        if (mutex is None) != (mutex_timeout is None):
            raise ValueError("give both the git mutex and how long to wait for it, or neither")
        super().__init__(repo, executable=executable, env=env, timeout=timeout, log_dir=log_dir)
        self._protected = protected
        self._mutex = mutex
        self._mutex_timeout = mutex_timeout

    async def run(self, *args: str) -> GitResult:
        command = check(args)
        if self._mutex is None or self._mutex_timeout is None or not writes(command):
            return await self._guarded_run(args, command.sub, command.flags)
        async with self._mutex.hold(timeout=self._mutex_timeout):
            return await self._guarded_run(args, command.sub, command.flags)

    async def _guarded_run(
        self, args: tuple[str, ...], sub: str, flags: frozenset[str]
    ) -> GitResult:
        rewrites = sub == "reset" or (sub == "commit" and "--amend" in flags)
        if sub in HEAD_WRITERS:
            await self._check_branch(args, rewrites=rewrites)
        return await super().run(*args)

    async def _check_branch(self, args: tuple[str, ...], *, rewrites: bool) -> None:
        head = await super().run("symbolic-ref", "-q", "HEAD")
        if head.exit_code != 0 or not head.lines:
            return  # detached HEAD: no named branch is written or rewritten
        branch = head.lines[0].removeprefix("refs/heads/")
        if self._protected.is_protected(branch):
            raise GitCommandRefused(args, f"{branch!r} is a protected branch")
        if rewrites:
            (tip,) = (await super().run("rev-parse", "HEAD")).lines
            published = await super().run(
                "for-each-ref", "--contains", tip, "--format=%(refname)", "refs/remotes"
            )
            if published.lines:
                raise GitCommandRefused(
                    args, f"{branch!r} is already published ({published.lines[0]}); history stays"
                )
