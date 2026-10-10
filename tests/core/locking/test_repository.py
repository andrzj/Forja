import asyncio
import shutil
import time
from pathlib import Path

import pytest

from forja.core.failures import TransientFailure
from forja.core.idempotency import Git
from forja.core.locking import (
    LockOwner,
    LockPolicy,
    LockWaitTimeout,
    RepositoryBusy,
    acquire_repository_lock,
    repository_id,
)
from forja.core.paths import locks_dir
from tests.core.idempotency.conftest import Repo
from tests.core.locking.support import NO_SLEEP, dead_owner, write_lock

REFUSE = LockPolicy.refuse()


def take(locks: Path, run_id: str, policy: LockPolicy = REFUSE, **kwargs):  # type: ignore[no-untyped-def]
    return acquire_repository_lock(
        locks, LockOwner.current(run_id), policy, settings=NO_SLEEP, **kwargs
    )


# -- who is the repository ---------------------------------------------------------------------


def test_the_repository_id_is_short_stable_and_shared_by_every_worktree(
    repo: Repo, tmp_path: Path
) -> None:
    worktree = tmp_path / "wt"
    repo.sh("worktree", "add", "--detach", str(worktree))

    main_id = asyncio.run(repository_id(repo.git))

    assert len(main_id) == 16 and int(main_id, 16) >= 0
    assert asyncio.run(repository_id(repo.git)) == main_id
    assert asyncio.run(repository_id(repo.git.at(worktree))) == main_id
    assert asyncio.run(repository_id(repo.git.at(repo.path / "." / "subdir" / ".."))) == main_id


def test_two_repositories_have_two_ids(repo: Repo, tmp_path: Path) -> None:
    other = tmp_path / "other"
    other.mkdir()
    repo.sh("init", "-b", "main", cwd=other)
    other_git = Git(
        other,
        executable=shutil.which("git") or "git",
        env=repo.env,
        timeout=30,
        log_dir=tmp_path / "l",
    )

    assert asyncio.run(repository_id(other_git)) != asyncio.run(repository_id(repo.git))


# -- one session per repository ----------------------------------------------------------------


def test_a_second_session_is_refused_with_the_holders_details(tmp_path: Path) -> None:
    async def scenario() -> None:
        first = await take(tmp_path, "run-a")
        with pytest.raises(RepositoryBusy) as info:
            await take(tmp_path, "run-b")
        assert info.value.owner == first.owner
        assert "run-a" in str(info.value)
        assert f"pid {first.owner.pid}" in str(info.value)

    asyncio.run(scenario())


def test_the_lock_is_released_with_the_context_manager_even_after_an_error(tmp_path: Path) -> None:
    async def scenario() -> None:
        with pytest.raises(RuntimeError), await take(tmp_path, "run-a"):
            raise RuntimeError("the run crashed")
        second = await take(tmp_path, "run-b")
        assert second.taken_over is None

    asyncio.run(scenario())


def test_an_abandoned_lock_is_taken_over_and_says_who_had_it(tmp_path: Path) -> None:
    gone = dead_owner(run_id="crashed-run")
    write_lock(tmp_path / "run.lock", gone)

    held = asyncio.run(take(tmp_path, "run-b"))

    assert held.taken_over is not None and held.taken_over.previous == gone


def test_a_session_can_tell_that_it_lost_its_lock(tmp_path: Path) -> None:
    held = asyncio.run(take(tmp_path, "run-a"))
    assert held.still_ours()

    shutil.rmtree(tmp_path / "run.lock")
    write_lock(tmp_path / "run.lock", dead_owner())

    assert not held.still_ours()
    assert held.release() is False


# -- waiting -----------------------------------------------------------------------------------


def test_waiting_gets_the_lock_as_soon_as_the_holder_lets_go(tmp_path: Path) -> None:
    async def scenario() -> float:
        first = await take(tmp_path, "run-a")
        asyncio.get_running_loop().call_later(0.3, first.release)
        started = time.monotonic()
        second = await take(tmp_path, "run-b", LockPolicy.wait_for(10, 0.05))
        assert second.owner.run_id == "run-b" and second.taken_over is None
        return time.monotonic() - started

    assert asyncio.run(scenario()) >= 0.25


def test_waiting_ends_at_once_when_the_holder_turns_out_to_be_dead(tmp_path: Path) -> None:
    write_lock(tmp_path / "run.lock", dead_owner())

    started = time.monotonic()
    held = asyncio.run(take(tmp_path, "run-b", LockPolicy.wait_for(30, 5)))

    assert time.monotonic() - started < 3
    assert held.taken_over is not None


def test_waiting_has_a_limit_and_running_out_is_a_transient_failure(tmp_path: Path) -> None:
    async def scenario() -> None:
        first = await take(tmp_path, "run-a")
        with pytest.raises(LockWaitTimeout) as info:
            await take(tmp_path, "run-b", LockPolicy.wait_for(0.3, 0.05))
        assert isinstance(info.value, TransientFailure)
        assert info.value.owner == first.owner
        assert info.value.waited >= 0.3
        assert not (tmp_path / "run.lock.takeover").exists()
        assert first.still_ours()  # waiting never disturbs the holder

    asyncio.run(scenario())


def test_the_wait_polls_at_the_interval_and_never_sleeps_past_the_limit(tmp_path: Path) -> None:
    now = 0.0
    slept: list[float] = []

    def clock() -> float:
        return now

    async def sleep(seconds: float) -> None:
        nonlocal now
        slept.append(seconds)
        now += seconds

    async def scenario() -> None:
        await take(tmp_path, "run-a")
        with pytest.raises(LockWaitTimeout):
            await take(tmp_path, "run-b", LockPolicy.wait_for(2.5, 1.0), sleep=sleep, clock=clock)

    asyncio.run(scenario())

    assert slept == [1.0, 1.0, 0.5]


def test_a_wait_needs_positive_limits() -> None:
    for timeout, poll in ((0, 1), (-1, 1), (5, 0), (5, -1)):
        with pytest.raises(ValueError, match="positive"):
            LockPolicy.wait_for(timeout, poll)
    assert not REFUSE.wait and REFUSE.timeout is None


def test_locks_of_different_repositories_do_not_meet(tmp_path: Path) -> None:
    async def scenario() -> None:
        await take(locks_dir("aaaa", environ={"FORJA_HOME": str(tmp_path)}), "run-a")
        await take(locks_dir("bbbb", environ={"FORJA_HOME": str(tmp_path)}), "run-b")

    asyncio.run(scenario())
    assert sorted(p.name for p in (tmp_path / "locks").iterdir()) == ["aaaa", "bbbb"]
