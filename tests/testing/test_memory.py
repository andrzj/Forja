"""The doubles in ``forja.testing`` held to their own behaviour.

The contract test holds them to git; these pin the details a contract scenario does not reach:
exact messages, exact payloads, and which sha a branch starts from.
"""

import asyncio
import re
import shutil
from collections.abc import Awaitable
from pathlib import Path
from typing import Any

import pytest

from forja.core.events import OpenOperation
from forja.core.gitguard.snapshot import Difference, DifferenceKind
from forja.core.idempotency import (
    Decision,
    ReconciliationError,
    run_branch_name,
    task_branch_name,
)
from forja.core.states import Level
from forja.orchestrator.workspace_git import (
    CommitMessage,
    IntegrationConflict,
    Layout,
    NothingToCommit,
    NothingToRollBack,
    RepositoryNotReady,
)
from forja.testing import MemoryRepo, MemoryWorkspace
from forja.testing.repo import MergeConflict, read_tree, write_tree
from forja.testing.workspace import MemoryWatch, _key

RUN = "run-1"
MESSAGE = CommitMessage("refactor: x", "why", "agent 1", "0.0.0+p")


def go[T](awaitable: Awaitable[T]) -> T:
    async def wait() -> T:
        return await awaitable

    return asyncio.run(wait())


@pytest.fixture
def repo() -> MemoryRepo:
    return MemoryRepo({"a.py": "one\n"})


@pytest.fixture
def ws(repo: MemoryRepo, tmp_path: Path) -> MemoryWorkspace:
    return MemoryWorkspace(repo, run_id=RUN, layout=Layout(tmp_path / "wt"))


def operation(name: str, **payload: Any) -> OpenOperation:
    return OpenOperation(name, f"{name}:x", Level.EXECUTION, "x", 1, payload=payload)


def verdict(ws: MemoryWorkspace, name: str, **payload: Any) -> Decision:
    return go(ws.reconcile(operation(name, **payload))).decision


# -- the repository ------------------------------------------------------------------------------


def test_shas_count_up_from_one(repo: MemoryRepo) -> None:
    assert repo.base == f"{1:040x}"
    assert repo.commit({}, "next", parents=(repo.base,)).sha == f"{2:040x}"


def test_a_commit_has_no_body_unless_given(repo: MemoryRepo) -> None:
    assert repo.commit({}, "s", parents=()).body == ""


def test_a_conflict_names_the_file(repo: MemoryRepo) -> None:
    mine = repo.commit({"a.py": "two\n"}, "m", parents=(repo.base,))
    yours = repo.commit({"a.py": "three\n"}, "y", parents=(repo.base,))
    with pytest.raises(MergeConflict, match=re.escape("a.py")):
        repo.merge_trees(mine.sha, yours.sha)


def test_a_tree_round_trips_with_non_ascii_text_and_unix_newlines(tmp_path: Path) -> None:
    write_tree(tmp_path / "t", {"d/e/ação.py": "linha\nnova\n"})
    assert (tmp_path / "t" / "d" / "e" / "ação.py").read_bytes() == b"linha\nnova\n"
    assert read_tree(tmp_path / "t") == {"d/e/ação.py": "linha\nnova\n"}


def test_an_empty_tree_still_makes_its_directory_and_the_ones_above_it(tmp_path: Path) -> None:
    write_tree(tmp_path / "no" / "such" / "dir", {})
    assert (tmp_path / "no" / "such" / "dir").is_dir()


# -- the watch -------------------------------------------------------------------------------------


def test_a_watch_that_has_seen_nothing_has_no_differences(repo: MemoryRepo) -> None:
    assert MemoryWatch(repo).differences == []


def test_leaving_a_watch_never_entered_sees_every_branch_as_new(repo: MemoryRepo) -> None:
    watch = MemoryWatch(repo)
    go(watch.__aexit__(None, None, None))
    assert watch.differences == [
        Difference(DifferenceKind.REF_ADDED, "refs/heads/main", None, repo.base)
    ]


def test_the_watch_names_added_moved_and_removed_branches_exactly(repo: MemoryRepo) -> None:
    repo.create_branch("gone")
    repo.create_branch("moves")
    watch = MemoryWatch(repo)
    other = repo.commit({"a.py": "x\n"}, "o", parents=(repo.base,))

    async def meddle() -> None:
        async with watch:
            del repo.branches["gone"]
            repo.advance("moves", other)
            repo.create_branch("new")

    go(meddle())
    assert watch.differences == [
        Difference(DifferenceKind.REF_REMOVED, "refs/heads/gone", repo.base, None),
        Difference(DifferenceKind.REF_MOVED, "refs/heads/moves", repo.base, other.sha),
        Difference(DifferenceKind.REF_ADDED, "refs/heads/new", None, repo.base),
    ]


# -- the workspace ---------------------------------------------------------------------------


def test_the_run_branch_is_named_for_the_run(ws: MemoryWorkspace) -> None:
    assert ws.run_branch == run_branch_name(RUN)


def test_a_clean_repository_is_ready_and_answers_with_its_tip(
    ws: MemoryWorkspace, repo: MemoryRepo
) -> None:
    assert go(ws.check_ready()) == repo.base


def test_a_dirty_repository_is_refused_with_the_git_workspace_message(ws: MemoryWorkspace) -> None:
    ws.dirty = True
    message = "1 path(s) have uncommitted changes; commit or stash them first"
    with pytest.raises(RepositoryNotReady, match=re.escape(message)):
        go(ws.check_ready())


def test_the_run_branch_starts_at_the_commit_it_is_given_and_says_so(
    ws: MemoryWorkspace, repo: MemoryRepo
) -> None:
    later = repo.commit({"a.py": "later\n"}, "later", parents=(repo.base,))
    step = ws.create_run_branch(later.sha)
    assert go(step.payload()) == {"branch": ws.run_branch, "base": later.sha}
    go(step.run())
    assert repo.branches[ws.run_branch] == later.sha


def test_a_task_branch_starts_where_the_run_branch_is(
    ws: MemoryWorkspace, repo: MemoryRepo
) -> None:
    ahead = repo.commit({"a.py": "ahead\n"}, "ahead", parents=(repo.base,))
    repo.create_branch(ws.run_branch, ahead.sha)
    go(ws.create_task_branch("t1").run())
    assert repo.branches[task_branch_name(RUN, "t1")] == ahead.sha


def _with_attempt(ws: MemoryWorkspace) -> Path:
    go(ws.create_run_branch(ws.repo.base).run())
    go(ws.create_task_branch("t1").run())
    step = ws.create_attempt_worktree("t1", "a1")
    go(step.run())
    return ws.attempt_worktree("a1")


def test_committing_nothing_says_which_attempt_changed_nothing(ws: MemoryWorkspace) -> None:
    _with_attempt(ws)
    with pytest.raises(NothingToCommit, match=re.escape("attempt a1 changed nothing")):
        go(ws.commit_stage("t1", "s1", "a1", MESSAGE).run())


def test_a_conflicting_integration_names_both_branches(
    ws: MemoryWorkspace, repo: MemoryRepo
) -> None:
    _with_attempt(ws)
    task = task_branch_name(RUN, "t1")
    repo.advance(ws.run_branch, repo.commit({"a.py": "run\n"}, "r", parents=(repo.base,)))
    repo.advance(task, repo.commit({"a.py": "task\n"}, "t", parents=(repo.base,)))
    with pytest.raises(
        IntegrationConflict, match=re.escape(f"{task} does not merge into {ws.run_branch}")
    ):
        go(ws.integrate_task("t1", "s").run())


def test_rolling_back_what_was_not_merged_says_so(ws: MemoryWorkspace) -> None:
    go(ws.create_run_branch(ws.repo.base).run())
    message = f"{ws.run_branch} does not end with the merge of t1"
    with pytest.raises(NothingToRollBack, match=re.escape(message)):
        go(ws.rollback_integration("t1").payload())


# -- settling an operation -------------------------------------------------------------------


def test_an_unknown_branch_is_reported_by_name(ws: MemoryWorkspace) -> None:
    with pytest.raises(ReconciliationError, match=re.escape("branch 'nope' does not exist")):
        verdict(ws, "integrate_task", task_branch="nope", run_branch="nope")


def test_an_attempt_worktree_is_done_only_with_the_right_head_and_the_directory(
    ws: MemoryWorkspace, repo: MemoryRepo
) -> None:
    path = _with_attempt(ws)
    here = {"worktree": str(path), "expected_head": repo.base}
    assert verdict(ws, "create_attempt_worktree", **here) is Decision.ALREADY_DONE
    elsewhere = {"worktree": str(path), "expected_head": "f" * 40}
    assert verdict(ws, "create_attempt_worktree", **elsewhere) is Decision.REDO
    shutil.rmtree(path)
    assert verdict(ws, "create_attempt_worktree", **here) is Decision.REDO


def test_a_worktree_is_gone_only_when_it_is_neither_registered_nor_on_disk(
    ws: MemoryWorkspace, repo: MemoryRepo, tmp_path: Path
) -> None:
    gone = tmp_path / "wt" / "gone"
    assert verdict(ws, "remove_worktree", worktree=str(gone)) is Decision.ALREADY_DONE
    on_disk = tmp_path / "wt" / "on_disk"
    on_disk.mkdir(parents=True)
    assert verdict(ws, "remove_worktree", worktree=str(on_disk)) is Decision.REDO
    registered = tmp_path / "wt" / "registered"
    repo.worktrees[_key(registered)] = repo.base
    assert verdict(ws, "remove_worktree", worktree=str(registered)) is Decision.REDO
