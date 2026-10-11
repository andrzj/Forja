import asyncio
import shutil
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import pytest

from forja.core.authorization import ProtectedBranches
from forja.core.gitguard import GitCommandRefused, GuardedGit, check, writes
from forja.core.idempotency import Git
from forja.core.locking import GitMutex, LockOwner, MutexTimeout
from tests.core.idempotency.conftest import Repo
from tests.core.locking.support import NO_SLEEP

PROTECTED = ProtectedBranches(frozenset({"main"}))


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        (["add", "-A"], True),
        (["commit", "-m", "x"], True),
        (["merge", "x"], True),
        (["fetch", "origin"], True),
        (["reset", "--hard"], True),
        (["checkout", "-b", "x"], True),
        (["switch", "x"], True),
        (["init"], True),
        (["branch", "x"], True),
        (["tag", "v1"], True),
        (["worktree", "add", "p"], True),
        (["worktree", "remove", "p"], True),
        (["worktree", "prune"], True),
        (["notes", "add", "-m", "m"], True),
        (["status"], False),
        (["log"], False),
        (["rev-parse", "HEAD"], False),
        (["show-ref", "--verify", "x"], False),
        (["for-each-ref"], False),
        (["ls-remote", "origin"], False),
        (["branch"], False),
        (["branch", "--list"], False),
        (["tag"], False),
        (["tag", "-l"], False),
        (["worktree", "list"], False),
        (["notes", "show", "HEAD"], False),
        (["config", "--get", "x"], False),
        (["symbolic-ref", "HEAD"], False),
        (["remote", "-v"], False),
    ],
    ids=lambda v: " ".join(v) if isinstance(v, list) else str(v),
)
def test_only_commands_that_write_take_the_mutex(args: list[str], expected: bool) -> None:
    assert writes(check(args)) is expected


class RecordingMutex(GitMutex):
    def __init__(self, locks: Path, events: list[str]) -> None:
        super().__init__(locks, LockOwner.current, settings=NO_SLEEP, poll_interval=0.01)
        self._events = events

    @asynccontextmanager
    async def hold(self, *, timeout: float) -> AsyncIterator[None]:
        self._events.append(f"mutex in (timeout {timeout:g})")
        async with super().hold(timeout=timeout):
            yield
        self._events.append("mutex out")


def make_guard(
    repo: Repo, tmp_path: Path, mutex: GitMutex | None, timeout: float | None
) -> GuardedGit:
    return GuardedGit(
        repo.path,
        executable=shutil.which("git") or "git",
        env={
            **repo.env,
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@example.com",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@example.com",
        },
        timeout=30,
        log_dir=tmp_path / "guard-logs",
        protected=PROTECTED,
        mutex=mutex,
        mutex_timeout=timeout,
    )


def test_a_writing_command_runs_inside_the_mutex_and_a_reading_one_does_not(
    repo: Repo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []
    original = Git.run

    async def spy(self: Git, *args: str):  # type: ignore[no-untyped-def]
        events.append(f"git {args[0]}")
        return await original(self, *args)

    monkeypatch.setattr(Git, "run", spy)
    guard = make_guard(repo, tmp_path, RecordingMutex(tmp_path / "locks", events), 7)
    repo.sh("checkout", "-b", "feature")

    asyncio.run(guard.run("rev-parse", "HEAD"))
    asyncio.run(guard.run("commit", "--allow-empty", "-m", "x"))

    assert events[0] == "git rev-parse"
    inside = events[1 : events.index("mutex out") + 1]
    assert inside[0] == "mutex in (timeout 7)"
    assert "git commit" in inside and inside[-1] == "mutex out"


def test_a_refused_command_never_waits_for_the_mutex(repo: Repo, tmp_path: Path) -> None:
    events: list[str] = []
    guard = make_guard(repo, tmp_path, RecordingMutex(tmp_path / "locks", events), 7)

    with pytest.raises(GitCommandRefused):
        asyncio.run(guard.run("branch", "-D", "main"))

    assert events == []


def test_a_busy_mutex_makes_a_writing_command_time_out_but_not_a_reading_one(
    repo: Repo, tmp_path: Path
) -> None:
    locks = tmp_path / "locks"
    holder = GitMutex(locks, LockOwner.current, settings=NO_SLEEP, poll_interval=0.01)
    guard = make_guard(
        repo,
        tmp_path,
        GitMutex(locks, LockOwner.current, settings=NO_SLEEP, poll_interval=0.01),
        0.2,
    )

    async def scenario() -> None:
        async with holder.hold(timeout=5):
            assert (await guard.run("rev-parse", "HEAD")).exit_code == 0
            with pytest.raises(MutexTimeout):
                await guard.run("add", "-A")
        assert (await guard.run("add", "-A")).exit_code == 0

    asyncio.run(scenario())


def test_the_mutex_and_its_timeout_come_together_or_not_at_all(repo: Repo, tmp_path: Path) -> None:
    mutex = GitMutex(tmp_path / "locks")

    with pytest.raises(ValueError, match="both"):
        make_guard(repo, tmp_path, mutex, None)
    with pytest.raises(ValueError, match="both"):
        make_guard(repo, tmp_path, None, 5)
    make_guard(repo, tmp_path, None, None)


def test_clones_for_other_directories_share_the_same_mutex(repo: Repo, tmp_path: Path) -> None:
    events: list[str] = []
    guard = make_guard(repo, tmp_path, RecordingMutex(tmp_path / "locks", events), 5)
    worktree = tmp_path / "wt"
    repo.sh("worktree", "add", "--detach", str(worktree))

    asyncio.run(guard.at(worktree).run("add", "-A"))

    assert events == ["mutex in (timeout 5)", "mutex out"]
