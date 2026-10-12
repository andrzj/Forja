"""One reconciliation test group per operation of the table; names start with the operation name."""

import asyncio
import shutil
from pathlib import Path

import pytest

from forja.core.idempotency import (
    Decision,
    Git,
    GitError,
    ReconciliationError,
    normalize_stage_id,
    reconcile_apply_diff,
    reconcile_call_agent_cli,
    reconcile_commit_stage,
    reconcile_create_attempt_worktree,
    reconcile_create_run_branch,
    reconcile_create_task_branch,
    reconcile_integrate_task,
    reconcile_normalize_style,
    reconcile_prepare_workcopy,
    reconcile_remove_worktree,
    reconcile_rollback_integration,
    reconcile_run_tool,
    run_branch_name,
    task_branch_name,
)
from forja.core.manifest import build_manifest
from tests.core.idempotency.conftest import Repo

DONE, REDO = Decision.ALREADY_DONE, Decision.REDO


def test_create_task_branch_exists_means_already_done(repo: Repo) -> None:
    branch = task_branch_name("run1", "task1")
    repo.sh("branch", branch)

    assert asyncio.run(reconcile_create_task_branch(repo.git, branch)).decision is DONE


def test_create_task_branch_missing_means_redo(repo: Repo) -> None:
    result = asyncio.run(reconcile_create_task_branch(repo.git, task_branch_name("run1", "task1")))

    assert result.decision is REDO


def test_create_task_branch_ignores_a_tag_with_the_same_name(repo: Repo) -> None:
    repo.sh("tag", "forja-task")

    assert asyncio.run(reconcile_create_task_branch(repo.git, "forja-task")).decision is REDO


def test_create_attempt_worktree_listed_on_disk_at_expected_commit_is_already_done(
    repo: Repo, tmp_path: Path
) -> None:
    worktree = tmp_path / "wt-a1"
    repo.sh("worktree", "add", "--detach", str(worktree))
    head = repo.sh("rev-parse", "HEAD")

    assert asyncio.run(reconcile_create_attempt_worktree(repo.git, worktree, head)).decision is DONE


def test_create_attempt_worktree_absent_means_redo(repo: Repo, tmp_path: Path) -> None:
    head = repo.sh("rev-parse", "HEAD")

    result = asyncio.run(reconcile_create_attempt_worktree(repo.git, tmp_path / "wt-a1", head))

    assert result.decision is REDO


def test_create_attempt_worktree_listed_but_deleted_from_disk_means_redo(
    repo: Repo, tmp_path: Path
) -> None:
    worktree = tmp_path / "wt-a1"
    repo.sh("worktree", "add", "--detach", str(worktree))
    head = repo.sh("rev-parse", "HEAD")
    shutil.rmtree(worktree)

    assert asyncio.run(reconcile_create_attempt_worktree(repo.git, worktree, head)).decision is REDO


def test_create_attempt_worktree_at_another_commit_means_redo(repo: Repo, tmp_path: Path) -> None:
    worktree = tmp_path / "wt-a1"
    repo.sh("worktree", "add", "--detach", str(worktree))
    old_head = repo.sh("rev-parse", "HEAD")
    repo.commit("later.txt")
    new_head = repo.sh("rev-parse", "HEAD")
    assert old_head != new_head

    assert (
        asyncio.run(reconcile_create_attempt_worktree(repo.git, worktree, new_head)).decision
        is REDO
    )


def _tree(root: Path, files: dict[str, bytes]) -> str:
    for name, data in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_bytes(data)
    return build_manifest(root).digest()


def test_prepare_workcopy_with_the_expected_content_is_already_done(tmp_path: Path) -> None:
    digest = _tree(tmp_path / "copy", {"a.py": b"a", "pkg/b.py": b"b"})

    assert reconcile_prepare_workcopy(tmp_path / "copy", digest).decision is DONE


def test_prepare_workcopy_ignores_what_forja_itself_put_in_the_copy(tmp_path: Path) -> None:
    digest = _tree(tmp_path / "copy", {"a.py": b"a"})
    (tmp_path / "copy" / ".forja-agent").mkdir()
    (tmp_path / "copy" / ".forja-agent" / "package.md").write_bytes(b"task")

    assert reconcile_prepare_workcopy(tmp_path / "copy", digest).decision is REDO
    verdict = reconcile_prepare_workcopy(tmp_path / "copy", digest, exclude={".forja-agent"})
    assert verdict.decision is DONE


@pytest.mark.parametrize("damage", ["missing_dir", "missing_file", "extra_file", "edited_file"])
def test_prepare_workcopy_partial_or_wrong_copy_means_redo(tmp_path: Path, damage: str) -> None:
    copy = tmp_path / "copy"
    digest = _tree(copy, {"a.py": b"a", "pkg/b.py": b"b"})
    if damage == "missing_dir":
        shutil.rmtree(copy)
    elif damage == "missing_file":
        (copy / "pkg" / "b.py").unlink()
    elif damage == "extra_file":
        (copy / "extra.py").write_bytes(b"x")
    else:
        (copy / "a.py").write_bytes(b"changed")

    assert reconcile_prepare_workcopy(copy, digest).decision is REDO


def test_call_agent_cli_is_never_verifiable_so_the_attempt_is_discarded_and_counted() -> None:
    result = reconcile_call_agent_cli()

    assert result.decision is Decision.DISCARD_ATTEMPT
    assert result.counts_as_infra_failure is True


def test_apply_diff_worktree_at_expected_manifest_is_already_done_ignoring_git_file(
    tmp_path: Path,
) -> None:
    expected = tmp_path / "expected"
    digest = _tree(expected, {"a.py": b"new"})
    worktree = tmp_path / "worktree"
    _tree(worktree, {"a.py": b"new", ".git": b"gitdir: somewhere"})

    assert reconcile_apply_diff(worktree, digest).decision is DONE


@pytest.mark.parametrize("state", ["not_applied", "half_applied"])
def test_apply_diff_not_or_partly_applied_means_redo(tmp_path: Path, state: str) -> None:
    digest = _tree(tmp_path / "expected", {"a.py": b"new", "b.py": b"new"})
    files = (
        {"a.py": b"old", "b.py": b"old"}
        if state == "not_applied"
        else {"a.py": b"new", "b.py": b"old"}
    )
    worktree = tmp_path / "worktree"
    _tree(worktree, files)

    assert reconcile_apply_diff(worktree, digest).decision is REDO


class _Index:
    def __init__(self, keys: set[str]) -> None:
        self._keys = keys

    def has(self, cache_key: str) -> bool:
        return cache_key in self._keys


def test_run_tool_with_evidence_for_the_same_key_is_reused() -> None:
    assert reconcile_run_tool(_Index({"k1"}), "k1").decision is DONE


def test_run_tool_without_evidence_for_the_key_runs_again() -> None:
    assert reconcile_run_tool(_Index({"other"}), "k1").decision is REDO


def _commit_with_trailers(repo: Repo, name: str, stage: str) -> None:
    (repo.path / name).write_text(name)
    repo.sh("add", name)
    repo.sh(
        "commit", "-m", f"feat: add file\n\nwhy\n\nTask-Id: t1\nStage-Id: {stage}\nAttempt-Id: a1"
    )


def test_commit_stage_with_the_stage_trailer_on_the_branch_is_already_done(repo: Repo) -> None:
    repo.sh("checkout", "-b", "forja/r/t1")
    _commit_with_trailers(repo, "x.txt", "stage-1")

    assert asyncio.run(reconcile_commit_stage(repo.git, "forja/r/t1", "stage-1")).decision is DONE


def test_commit_stage_for_another_stage_means_redo(repo: Repo) -> None:
    repo.sh("checkout", "-b", "forja/r/t1")
    _commit_with_trailers(repo, "x.txt", "stage-1")

    assert asyncio.run(reconcile_commit_stage(repo.git, "forja/r/t1", "stage-2")).decision is REDO


def test_commit_stage_text_that_only_looks_like_a_trailer_does_not_count(repo: Repo) -> None:
    repo.sh("checkout", "-b", "forja/r/t1")
    (repo.path / "x.txt").write_text("x")
    repo.sh("add", "x.txt")
    repo.sh("commit", "-m", "fix: thing\n\nStage-Id: stage-1\n\nthis line ends the paragraph")

    assert asyncio.run(reconcile_commit_stage(repo.git, "forja/r/t1", "stage-1")).decision is REDO


def test_commit_stage_prefix_of_a_stage_id_is_not_a_match(repo: Repo) -> None:
    repo.sh("checkout", "-b", "forja/r/t1")
    _commit_with_trailers(repo, "x.txt", "stage-10")

    assert asyncio.run(reconcile_commit_stage(repo.git, "forja/r/t1", "stage-1")).decision is REDO


def test_commit_stage_cannot_be_verified_without_the_branch(repo: Repo) -> None:
    with pytest.raises(ReconciliationError):
        asyncio.run(reconcile_commit_stage(repo.git, "forja/r/missing", "stage-1"))


def _task_branch_with_commit(repo: Repo) -> None:
    repo.sh("checkout", "-b", "forja/r/t1")
    repo.commit("task.txt")
    repo.sh("checkout", "main")


def test_integrate_task_branch_contained_in_the_run_branch_is_already_done(repo: Repo) -> None:
    _task_branch_with_commit(repo)
    repo.sh("merge", "--no-ff", "-m", "integrate", "forja/r/t1")

    assert asyncio.run(reconcile_integrate_task(repo.git, "forja/r/t1", "main")).decision is DONE


def test_integrate_task_branch_not_yet_in_the_run_branch_means_redo(repo: Repo) -> None:
    _task_branch_with_commit(repo)

    assert asyncio.run(reconcile_integrate_task(repo.git, "forja/r/t1", "main")).decision is REDO


def test_integrate_task_run_branch_that_moved_on_still_contains_the_task(repo: Repo) -> None:
    _task_branch_with_commit(repo)
    repo.sh("merge", "--no-ff", "-m", "integrate", "forja/r/t1")
    repo.commit("later.txt")

    assert asyncio.run(reconcile_integrate_task(repo.git, "forja/r/t1", "main")).decision is DONE


def test_integrate_task_cannot_be_verified_without_both_branches(repo: Repo) -> None:
    with pytest.raises(ReconciliationError):
        asyncio.run(reconcile_integrate_task(repo.git, "forja/r/missing", "main"))
    with pytest.raises(ReconciliationError):
        asyncio.run(reconcile_integrate_task(repo.git, "main", "missing"))


def test_remove_worktree_gone_from_disk_and_list_is_already_done(
    repo: Repo, tmp_path: Path
) -> None:
    worktree = tmp_path / "wt"
    repo.sh("worktree", "add", "--detach", str(worktree))
    repo.sh("worktree", "remove", "--force", str(worktree))

    assert asyncio.run(reconcile_remove_worktree(repo.git, worktree)).decision is DONE


def test_remove_worktree_still_present_means_redo(repo: Repo, tmp_path: Path) -> None:
    worktree = tmp_path / "wt"
    repo.sh("worktree", "add", "--detach", str(worktree))

    assert asyncio.run(reconcile_remove_worktree(repo.git, worktree)).decision is REDO


def test_remove_worktree_deleted_from_disk_but_still_registered_means_redo(
    repo: Repo, tmp_path: Path
) -> None:
    worktree = tmp_path / "wt"
    repo.sh("worktree", "add", "--detach", str(worktree))
    shutil.rmtree(worktree)

    assert asyncio.run(reconcile_remove_worktree(repo.git, worktree)).decision is REDO


def test_branch_names_carry_the_run_id() -> None:
    assert run_branch_name("r1") == "forja-run/r1"
    assert normalize_stage_id("r1") == "normalize-r1"
    assert run_branch_name("r1") != task_branch_name("r1", "t1").rsplit("/", 1)[0]


def test_create_run_branch_exists_means_already_done(repo: Repo) -> None:
    repo.sh("branch", run_branch_name("r1"))

    assert (
        asyncio.run(reconcile_create_run_branch(repo.git, run_branch_name("r1"))).decision is DONE
    )


def test_create_run_branch_missing_means_redo(repo: Repo) -> None:
    result = asyncio.run(reconcile_create_run_branch(repo.git, run_branch_name("r1")))

    assert result.decision is REDO


def test_create_run_branch_ignores_a_tag_with_the_same_name(repo: Repo) -> None:
    repo.sh("tag", "forja-run-r1")

    assert asyncio.run(reconcile_create_run_branch(repo.git, "forja-run-r1")).decision is REDO


def test_normalize_style_with_the_trailer_of_this_run_on_its_branch_is_already_done(
    repo: Repo,
) -> None:
    branch = run_branch_name("r1")
    repo.sh("checkout", "-b", branch)
    _commit_with_trailers(repo, "x.txt", normalize_stage_id("r1"))

    result = asyncio.run(reconcile_normalize_style(repo.git, branch, normalize_stage_id("r1")))

    assert result.decision is DONE


def test_normalize_style_of_another_run_does_not_count(repo: Repo) -> None:
    branch = run_branch_name("r2")
    repo.sh("checkout", "-b", branch)
    _commit_with_trailers(repo, "x.txt", normalize_stage_id("r1"))

    result = asyncio.run(reconcile_normalize_style(repo.git, branch, normalize_stage_id("r2")))

    assert result.decision is REDO


def test_normalize_style_cannot_be_verified_without_the_run_branch(repo: Repo) -> None:
    with pytest.raises(ReconciliationError):
        asyncio.run(
            reconcile_normalize_style(repo.git, run_branch_name("r1"), normalize_stage_id("r1"))
        )


def test_rollback_integration_with_the_tip_back_where_it_was_is_already_done(repo: Repo) -> None:
    before = repo.sh("rev-parse", "HEAD")
    repo.sh("checkout", "-b", run_branch_name("r1"))

    result = asyncio.run(reconcile_rollback_integration(repo.git, run_branch_name("r1"), before))

    assert result.decision is DONE


def test_rollback_integration_with_the_integration_still_in_place_means_redo(repo: Repo) -> None:
    before = repo.sh("rev-parse", "HEAD")
    repo.sh("checkout", "-b", run_branch_name("r1"))
    repo.commit("integrated.txt")

    result = asyncio.run(reconcile_rollback_integration(repo.git, run_branch_name("r1"), before))

    assert result.decision is REDO


def test_rollback_integration_cannot_be_verified_without_the_run_branch(repo: Repo) -> None:
    with pytest.raises(ReconciliationError):
        asyncio.run(reconcile_rollback_integration(repo.git, run_branch_name("r1"), "a" * 40))


def test_the_logs_of_git_are_numbered_from_one(repo: Repo, tmp_path: Path) -> None:
    asyncio.run(repo.git.run("rev-parse", "HEAD"))

    assert (tmp_path / "logs" / "git-1.log").is_file()
    assert not (tmp_path / "logs" / "git-0.log").exists()


def test_a_git_that_takes_too_long_is_an_error_not_a_result(repo: Repo, tmp_path: Path) -> None:
    import sys  # noqa: PLC0415

    slow = Git(
        repo.path, executable=sys.executable, env=repo.env, timeout=1, log_dir=tmp_path / "slow"
    )

    with pytest.raises(GitError, match="timed_out"):
        asyncio.run(slow.run("-c", "import time; time.sleep(30)"))
