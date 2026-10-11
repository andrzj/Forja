"""Verdicts for operations that have an intent but no recorded effect.

Each function answers one row of the table in ``operations``. They only look; repairing
partial work (removing a half-made worktree, erasing a half-copied tree) is done by the
operation itself when the orchestrator repeats it.
"""

import os
from pathlib import Path
from typing import Protocol

from forja.core.idempotency.git import Git
from forja.core.idempotency.outcome import Decision, Reconciliation, ReconciliationError
from forja.core.manifest import build_manifest

_DONE = Reconciliation(Decision.ALREADY_DONE)
_REDO = Reconciliation(Decision.REDO)


def task_branch_name(run_id: str, task_id: str) -> str:
    return f"forja/{run_id}/{task_id}"


class EvidenceIndex(Protocol):
    def has(self, cache_key: str) -> bool: ...


def _verdict(done: bool) -> Reconciliation:
    return _DONE if done else _REDO


async def _require_branch(git: Git, branch: str) -> None:
    if not await git.succeeds("rev-parse", "--verify", "--quiet", f"refs/heads/{branch}"):
        raise ReconciliationError(f"branch {branch!r} does not exist")


async def reconcile_create_task_branch(git: Git, branch: str) -> Reconciliation:
    return _verdict(await git.succeeds("show-ref", "--verify", "--quiet", f"refs/heads/{branch}"))


def run_branch_name(run_id: str) -> str:
    return f"forja-run/{run_id}"


def normalize_stage_id(run_id: str) -> str:
    return f"normalize-{run_id}"


async def reconcile_create_run_branch(git: Git, branch: str) -> Reconciliation:
    """Same rule as a task branch: the ref exists or it does not."""
    return await reconcile_create_task_branch(git, branch)


async def reconcile_normalize_style(git: Git, run_branch: str, stage_id: str) -> Reconciliation:
    """Same rule as a stage commit: the trailer says whether the normalization was committed."""
    return await reconcile_commit_stage(git, run_branch, stage_id)


async def reconcile_rollback_integration(
    git: Git, run_branch: str, expected_tip: str
) -> Reconciliation:
    await _require_branch(git, run_branch)
    (tip,) = await git.lines("rev-parse", f"refs/heads/{run_branch}")
    return _verdict(tip == expected_tip)


async def _listed_worktrees(git: Git) -> dict[str, str]:
    """Map of normalized worktree path to its HEAD commit."""
    found: dict[str, str] = {}
    path: str | None = None
    for line in await git.lines("worktree", "list", "--porcelain"):
        if line.startswith("worktree "):
            path = _normalize(line.removeprefix("worktree "))
        elif line.startswith("HEAD ") and path is not None:
            found[path] = line.removeprefix("HEAD ")
    return found


def _normalize(path: str | Path) -> str:
    return os.path.normcase(os.path.realpath(path))


async def reconcile_create_attempt_worktree(
    git: Git, worktree: Path, expected_head: str
) -> Reconciliation:
    head = (await _listed_worktrees(git)).get(_normalize(worktree))
    return _verdict(head == expected_head and worktree.is_dir())


def reconcile_prepare_workcopy(workcopy: Path, expected_digest: str) -> Reconciliation:
    return _verdict(workcopy.is_dir() and build_manifest(workcopy).digest() == expected_digest)


def reconcile_call_agent_cli() -> Reconciliation:
    """Never verifiable and never safe to repeat: drop the attempt and count the infra failure."""
    return Reconciliation(Decision.DISCARD_ATTEMPT, counts_as_infra_failure=True)


def reconcile_apply_diff(worktree: Path, expected_digest: str) -> Reconciliation:
    done = (
        worktree.is_dir() and build_manifest(worktree, exclude={".git"}).digest() == expected_digest
    )
    return _verdict(done)


def reconcile_run_tool(index: EvidenceIndex, cache_key: str) -> Reconciliation:
    return _verdict(index.has(cache_key))


async def reconcile_commit_stage(git: Git, task_branch: str, stage_id: str) -> Reconciliation:
    await _require_branch(git, task_branch)
    values = await git.lines(
        "log", task_branch, "--format=%(trailers:key=Stage-Id,valueonly,separator=%x0a)"
    )
    return _verdict(stage_id in {value.strip() for value in values})


async def reconcile_integrate_task(git: Git, task_branch: str, run_branch: str) -> Reconciliation:
    await _require_branch(git, task_branch)
    await _require_branch(git, run_branch)
    contained = await git.succeeds("merge-base", "--is-ancestor", task_branch, run_branch)
    return _verdict(contained)


async def reconcile_remove_worktree(git: Git, worktree: Path) -> Reconciliation:
    listed = _normalize(worktree) in await _listed_worktrees(git)
    return _verdict(not listed and not worktree.exists())


async def reconcile_push_run_branch(git: Git, remote: str, branch: str) -> Reconciliation:
    await _require_branch(git, branch)
    (local,) = await git.lines("rev-parse", f"refs/heads/{branch}")
    remote_lines = await git.lines("ls-remote", remote, f"refs/heads/{branch}")
    remote_tip = remote_lines[0].split()[0] if remote_lines else None
    return _verdict(remote_tip == local)
