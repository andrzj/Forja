from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType


class Action(StrEnum):
    """Things Forja does once the run is confirmed. Objective, CLI and budget are configuration."""

    READ_REPOSITORY = "read_repository"
    CREATE_WORKTREE = "create_worktree"
    REMOVE_WORKTREE = "remove_worktree"
    RUN_ADAPTER = "run_adapter"
    SEND_PACKAGE = "send_package"
    COMMIT_TO_TASK_BRANCH = "commit_to_task_branch"
    INTEGRATE_INTO_RUN_BRANCH = "integrate_into_run_branch"
    PUSH = "push"
    MERGE_INTO_PROTECTED_BRANCH = "merge_into_protected_branch"
    DELETE_BRANCH = "delete_branch"
    REWRITE_PUBLISHED_HISTORY = "rewrite_published_history"
    SEND_SENSITIVE_FILE = "send_sensitive_file"
    EXPOSE_SECRETS_TO_AGENT = "expose_secrets_to_agent"


class ActionClass(StrEnum):
    AUTOMATIC = "automatic"  # always allowed
    FORBIDDEN = "forbidden"  # never allowed, whatever the user said


A, F = ActionClass.AUTOMATIC, ActionClass.FORBIDDEN

CLASSIFICATION: Mapping[Action, ActionClass] = MappingProxyType(
    {
        Action.READ_REPOSITORY: A,
        Action.CREATE_WORKTREE: A,
        Action.REMOVE_WORKTREE: A,
        Action.RUN_ADAPTER: A,
        Action.SEND_PACKAGE: A,
        Action.COMMIT_TO_TASK_BRANCH: A,
        Action.INTEGRATE_INTO_RUN_BRANCH: A,
        Action.PUSH: F,
        Action.MERGE_INTO_PROTECTED_BRANCH: F,
        Action.DELETE_BRANCH: F,
        Action.REWRITE_PUBLISHED_HISTORY: F,
        Action.SEND_SENSITIVE_FILE: F,
        Action.EXPOSE_SECRETS_TO_AGENT: F,
    }
)

# Actions that always concern one branch, which must then be named in the request.
BRANCH_ACTIONS = frozenset({Action.COMMIT_TO_TASK_BRANCH, Action.INTEGRATE_INTO_RUN_BRANCH})


@dataclass(frozen=True)
class ActionRequest:
    """What is about to happen: the action, the branch it touches and the files it would send."""

    action: Action
    branch: str | None = None
    paths: tuple[str, ...] = ()
