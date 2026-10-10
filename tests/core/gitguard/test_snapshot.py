"""Every way an agent could change git is noticed; harmless activity is not."""

import asyncio
from collections.abc import Callable
from pathlib import Path

import pytest

from forja.core.gitguard import (
    Difference,
    DifferenceKind,
    GitSnapshot,
    GitWatch,
    compare_snapshots,
    take_snapshot,
)
from tests.core.idempotency.conftest import Repo

K = DifferenceKind


def snapshot(repo: Repo) -> GitSnapshot:
    return asyncio.run(take_snapshot(repo.git))


def changes(repo: Repo, act: Callable[[], object]) -> list[Difference]:
    before = snapshot(repo)
    act()
    return compare_snapshots(before, snapshot(repo))


def kinds(found: list[Difference]) -> set[DifferenceKind]:
    return {d.kind for d in found}


def subjects(found: list[Difference], kind: DifferenceKind) -> set[str]:
    return {d.subject for d in found if d.kind is kind}


# -- nothing changed ---------------------------------------------------------------------------


def test_two_snapshots_of_an_untouched_repository_are_equal(repo: Repo) -> None:
    assert snapshot(repo) == snapshot(repo)


def test_harmless_activity_is_not_a_change(repo: Repo) -> None:
    def busy() -> None:
        (repo.path / "base.txt").write_text("edited in the working tree")
        (repo.path / "untracked.txt").write_text("new")
        repo.sh("status")  # git may refresh the index bytes; the meaning is the same
        repo.sh("diff")

    assert changes(repo, busy) == []


# -- everything that is a change ---------------------------------------------------------------


def test_a_new_commit_moves_the_branch_and_the_head(repo: Repo) -> None:
    found = changes(repo, lambda: repo.commit("new.txt"))

    assert subjects(found, K.REF_MOVED) == {"refs/heads/main"}
    assert K.HEAD_CHANGED in kinds(found)


def test_a_new_branch_a_new_tag_and_a_deleted_branch(repo: Repo) -> None:
    repo.sh("branch", "doomed")

    assert subjects(changes(repo, lambda: repo.sh("branch", "other")), K.REF_ADDED) == {
        "refs/heads/other"
    }
    assert subjects(changes(repo, lambda: repo.sh("tag", "v1")), K.REF_ADDED) == {"refs/tags/v1"}
    assert subjects(changes(repo, lambda: repo.sh("branch", "-D", "doomed")), K.REF_REMOVED) == {
        "refs/heads/doomed"
    }


def test_a_stash_is_a_ref(repo: Repo) -> None:
    (repo.path / "base.txt").write_text("changed")

    found = changes(repo, lambda: repo.sh("stash"))

    assert "refs/stash" in subjects(found, K.REF_ADDED)


def test_staging_a_file_changes_the_index(repo: Repo) -> None:
    (repo.path / "staged.txt").write_text("x")

    found = changes(repo, lambda: repo.sh("add", "staged.txt"))

    assert kinds(found) == {K.INDEX_CHANGED}


def test_switching_branch_changes_the_branch_and_the_head(repo: Repo) -> None:
    repo.sh("checkout", "-b", "other")
    repo.commit("other.txt")

    found = changes(repo, lambda: repo.sh("checkout", "main"))

    assert {K.BRANCH_CHANGED, K.HEAD_CHANGED} <= kinds(found)


def test_a_new_alias_or_a_new_hook_is_noticed(repo: Repo) -> None:
    assert kinds(changes(repo, lambda: repo.sh("config", "alias.x", "status"))) == {
        K.CONFIG_CHANGED
    }

    def plant_hook() -> None:
        hook = repo.path / ".git" / "hooks" / "pre-commit"
        hook.write_text("#!/bin/sh\necho planted\n")

    assert kinds(changes(repo, plant_hook)) == {K.HOOKS_CHANGED}


def test_editing_an_existing_hook_is_noticed_too(repo: Repo) -> None:
    hook = repo.path / ".git" / "hooks" / "pre-commit"
    hook.write_text("#!/bin/sh\nexit 0\n")

    assert kinds(changes(repo, lambda: hook.write_text("#!/bin/sh\necho changed\n"))) == {
        K.HOOKS_CHANGED
    }


def test_worktrees_that_come_and_go(repo: Repo, tmp_path: Path) -> None:
    worktree = tmp_path / "wt"

    added = changes(repo, lambda: repo.sh("worktree", "add", "--detach", str(worktree)))
    removed = changes(repo, lambda: repo.sh("worktree", "remove", "--force", str(worktree)))

    assert kinds(added) == {K.WORKTREE_ADDED}
    assert kinds(removed) == {K.WORKTREE_REMOVED}


def test_work_inside_a_linked_worktree_is_seen_from_the_main_repository(
    repo: Repo, tmp_path: Path
) -> None:
    worktree = tmp_path / "wt"
    repo.sh("worktree", "add", "-b", "wt-branch", str(worktree))
    (worktree / "w.txt").write_text("w")

    staged = changes(repo, lambda: repo.sh("add", "w.txt", cwd=worktree))
    committed = changes(repo, lambda: repo.sh("commit", "-m", "in worktree", cwd=worktree))

    assert {Path(s).resolve() for s in subjects(staged, K.INDEX_CHANGED)} == {worktree.resolve()}
    assert subjects(committed, K.REF_MOVED) == {"refs/heads/wt-branch"}  # shared ref
    assert {Path(s).resolve() for s in subjects(committed, K.HEAD_CHANGED)} == {worktree.resolve()}


def test_a_fetch_that_moves_remote_tracking_refs_is_a_change(
    repo: Repo, new_remote: Callable[[], Path]
) -> None:
    remote = new_remote()
    repo.sh("remote", "add", "origin", str(remote))
    repo.sh("push", "origin", "main")

    first = changes(repo, lambda: repo.sh("fetch", "origin"))
    assert subjects(first, K.REF_ADDED) == {
        "refs/remotes/origin/HEAD"
    }  # git records the remote HEAD
    assert changes(repo, lambda: repo.sh("fetch", "origin")) == []  # nothing new the second time

    repo.commit("more.txt")
    moved = changes(repo, lambda: repo.sh("push", "origin", "main"))
    assert subjects(moved, K.REF_MOVED) == {  # origin/HEAD is a symbolic ref to origin/main
        "refs/remotes/origin/main",
        "refs/remotes/origin/HEAD",
    }


# -- the watch and the report ------------------------------------------------------------------


def test_the_watch_reports_no_difference_when_the_agent_only_touched_its_own_copy(
    repo: Repo, tmp_path: Path
) -> None:
    async def scenario() -> list[Difference]:
        async with GitWatch(repo.git) as watch:
            (tmp_path / "agent-copy.txt").write_text("work")
        return watch.differences

    assert asyncio.run(scenario()) == []


def test_the_watch_collects_differences_even_when_the_block_fails(repo: Repo) -> None:
    holder: list[GitWatch] = []

    async def scenario() -> None:
        async with GitWatch(repo.git) as watch:
            holder.append(watch)
            repo.sh("branch", "sneaky")
            raise RuntimeError("the agent crashed")

    with pytest.raises(RuntimeError, match="crashed"):
        asyncio.run(scenario())

    assert subjects(holder[0].differences, K.REF_ADDED) == {"refs/heads/sneaky"}


def test_differences_can_be_described_for_the_rejection_message() -> None:
    assert Difference(K.REF_MOVED, "refs/heads/main", "aaa", "bbb").describe() == (
        "ref_moved refs/heads/main: aaa -> bbb"
    )
    assert Difference(K.CONFIG_CHANGED, "config").describe() == "config_changed config"
