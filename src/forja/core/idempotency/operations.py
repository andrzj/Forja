"""The idempotency table of contract 2, one rule per external operation.

No operation enters Forja without a row here and a reconciliation test.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType


class OperationName(StrEnum):
    CREATE_RUN_BRANCH = "create_run_branch"
    NORMALIZE_STYLE = "normalize_style"
    CREATE_TASK_BRANCH = "create_task_branch"
    CREATE_ATTEMPT_WORKTREE = "create_attempt_worktree"
    PREPARE_WORKCOPY = "prepare_workcopy"
    CALL_AGENT_CLI = "call_agent_cli"
    APPLY_DIFF = "apply_diff"
    RUN_TOOL = "run_tool"
    COMMIT_STAGE = "commit_stage"
    INTEGRATE_TASK = "integrate_task"
    ROLLBACK_INTEGRATION = "rollback_integration"
    REMOVE_WORKTREE = "remove_worktree"
    PUSH_RUN_BRANCH = "push_run_branch"


@dataclass(frozen=True)
class OperationRule:
    name: OperationName
    identifier: str
    verification: str  # how to tell whether it already happened; "" when it cannot be told
    repeat_safe: bool
    reconciliation: str


_RULES = (
    OperationRule(
        OperationName.CREATE_RUN_BRANCH,
        "run id in the branch name",
        "the ref exists",
        True,
        "recreate if missing",
    ),
    OperationRule(
        OperationName.NORMALIZE_STYLE,
        "Stage-Id trailer normalize-<run id>",
        "a commit with that Stage-Id is on the run branch",
        False,
        "record the effect if it exists; otherwise normalize and commit again",
    ),
    OperationRule(
        OperationName.CREATE_TASK_BRANCH,
        "task id in the branch name",
        "the ref exists",
        True,
        "recreate if missing",
    ),
    OperationRule(
        OperationName.CREATE_ATTEMPT_WORKTREE,
        "attempt id in the path",
        "the worktree is listed, exists on disk and sits at the expected commit",
        True,
        "remove the partial one and recreate",
    ),
    OperationRule(
        OperationName.PREPARE_WORKCOPY,
        "attempt id",
        "manifest digest of the copy equals the expected one",
        True,
        "erase and copy again",
    ),
    OperationRule(
        OperationName.CALL_AGENT_CLI,
        "attempt id",
        "",
        False,
        "discard the attempt; the new one counts toward the infrastructure limit",
    ),
    OperationRule(
        OperationName.APPLY_DIFF,
        "digest of the expected manifest",
        "manifest digest of the worktree equals the expected one",
        True,
        "restore the worktree and apply again",
    ),
    OperationRule(
        OperationName.RUN_TOOL,
        "cache key (contract 5)",
        "evidence with the same key exists",
        True,
        "reuse it or run again",
    ),
    OperationRule(
        OperationName.COMMIT_STAGE,
        "Task-Id, Stage-Id and Attempt-Id trailers",
        "a commit with the Stage-Id trailer is on the task branch",
        False,
        "record the effect if it exists; otherwise commit again",
    ),
    OperationRule(
        OperationName.INTEGRATE_TASK,
        "task id",
        "the task branch tip is contained in the run branch",
        False,
        "record the effect if it exists; otherwise integrate and run the integration gate",
    ),
    OperationRule(
        OperationName.ROLLBACK_INTEGRATION,
        "task id",
        "the run branch tip is the commit it had before the integration",
        True,
        "move the run branch back to that commit",
    ),
    OperationRule(
        OperationName.REMOVE_WORKTREE,
        "path",
        "absent from disk and from the worktree list",
        True,
        "prune stale worktree records and remove again",
    ),
    OperationRule(
        OperationName.PUSH_RUN_BRANCH,
        "branch name",
        "the remote ref points to the expected commit",
        True,
        "push again",
    ),
)

OPERATIONS: Mapping[OperationName, OperationRule] = MappingProxyType(
    {rule.name: rule for rule in _RULES}
)
