"""What the orchestrator needs from the world, as protocols. Each port gets its implementation in
its own piece of increment 1; tests bring their own."""

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Protocol

from forja.core.events import OpenOperation
from forja.core.gitguard import GitWatch
from forja.core.idempotency import Reconciliation
from forja.core.locking import IndexLockReport
from forja.orchestrator.operations import Step
from forja.orchestrator.workspace_git import CommitMessage


class Workspace(Protocol):
    """Git, seen as steps the journal can run once and a way to settle them after a crash."""

    run_branch: str

    async def check_ready(self) -> str: ...

    async def recover(self) -> IndexLockReport: ...

    def watch(self) -> GitWatch: ...

    def create_run_branch(self, base_commit: str) -> Step: ...

    def create_run_worktree(self) -> Step: ...

    def normalize_style(self, apply: Callable[[Path], Awaitable[None]]) -> Step: ...

    def create_task_branch(self, task_id: str) -> Step: ...

    def create_attempt_worktree(self, task_id: str, attempt_id: str) -> Step: ...

    def commit_stage(
        self, task_id: str, stage_id: str, attempt_id: str, message: CommitMessage
    ) -> Step: ...

    def integrate_task(self, task_id: str, subject: str) -> Step: ...

    def rollback_integration(self, task_id: str) -> Step: ...

    def remove_worktree(self, name: str) -> Step: ...

    async def reconcile(self, operation: OpenOperation) -> Reconciliation: ...
