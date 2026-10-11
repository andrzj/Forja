"""The authorization table of contract 3, written out by hand and checked action by action."""

import itertools

import pytest

from forja.core.authorization import (
    CLASSIFICATION,
    Action,
    ActionClass,
    ActionForbidden,
    ActionRequest,
    ProtectedBranches,
    authorize,
)
from forja.core.isolation import SensitivePaths

PROTECTED = ProtectedBranches(frozenset({"main"}))
SENSITIVE = SensitivePaths.with_defaults(case_insensitive=False)

# Transcribed from the spec: automatic or forbidden. Nothing needs a grant: Forja never pushes.
SPEC = {
    "read_repository": "automatic",
    "create_worktree": "automatic",
    "remove_worktree": "automatic",
    "run_adapter": "automatic",
    "send_package": "automatic",
    "commit_to_task_branch": "automatic",
    "integrate_into_run_branch": "automatic",
    "push": "forbidden",
    "merge_into_protected_branch": "forbidden",
    "delete_branch": "forbidden",
    "rewrite_published_history": "forbidden",
    "send_sensitive_file": "forbidden",
    "expose_secrets_to_agent": "forbidden",
}
BRANCH_ACTIONS = {"commit_to_task_branch", "integrate_into_run_branch"}


def test_every_action_is_classified_as_the_spec_says() -> None:
    assert {a.value for a in Action} == set(SPEC)
    assert {a.value: c.value for a, c in CLASSIFICATION.items()} == SPEC


def test_there_are_only_two_classes() -> None:
    assert {c.value for c in ActionClass} == {"automatic", "forbidden"}


def request(action: Action, *, protected: bool = False, sensitive: bool = False) -> ActionRequest:
    branch = ("main" if protected else "forja/run1/t1") if action.value in BRANCH_ACTIONS else None
    paths = ("src/a.py", ".env") if sensitive else ("src/a.py", "README.md")
    return ActionRequest(action, branch, paths if action is Action.SEND_PACKAGE else ())


def expected(action: Action, *, protected: bool, sensitive: bool) -> bool:
    if SPEC[action.value] == "forbidden":
        return False
    if action.value in BRANCH_ACTIONS and protected:
        return False
    return not (action is Action.SEND_PACKAGE and sensitive)


CASES = [
    pytest.param(a, p, s, id=f"{a.value}|protected={p}|sensitive={s}")
    for a, p, s in itertools.product(Action, (False, True), (False, True))
]


@pytest.mark.parametrize(("action", "protected", "sensitive"), CASES)
def test_every_combination_is_decided_as_the_spec_says(
    action: Action, protected: bool, sensitive: bool
) -> None:
    def call() -> None:
        authorize(
            request(action, protected=protected, sensitive=sensitive),
            protected=PROTECTED,
            sensitive=SENSITIVE,
        )

    if expected(action, protected=protected, sensitive=sensitive):
        call()
    else:
        with pytest.raises(ActionForbidden) as info:
            call()
        assert info.value.action is action


def test_a_forbidden_action_is_refused_in_words() -> None:
    for action in (a for a in Action if CLASSIFICATION[a] is ActionClass.FORBIDDEN):
        with pytest.raises(ActionForbidden) as info:
            authorize(ActionRequest(action), protected=PROTECTED, sensitive=SENSITIVE)
        assert info.value.reason == "this action is never allowed"
        assert str(info.value) == f"{action.value} is not allowed: this action is never allowed"


def test_a_push_is_refused_whatever_the_branch() -> None:
    for branch in ("main", "forja-run/r1", None):
        with pytest.raises(ActionForbidden, match="never allowed"):
            authorize(ActionRequest(Action.PUSH, branch), protected=PROTECTED, sensitive=SENSITIVE)


def test_an_action_on_a_branch_must_say_which_branch() -> None:
    with pytest.raises(ValueError, match="needs the branch"):
        authorize(
            ActionRequest(Action.COMMIT_TO_TASK_BRANCH),
            protected=PROTECTED,
            sensitive=SENSITIVE,
        )


def test_the_denial_names_the_sensitive_files_and_becomes_a_loggable_payload() -> None:
    with pytest.raises(ActionForbidden) as info:
        authorize(
            ActionRequest(Action.SEND_PACKAGE, paths=("src/a.py", "config/.env", "keys/x.pem")),
            protected=PROTECTED,
            sensitive=SENSITIVE,
        )

    assert "config/.env, keys/x.pem" in info.value.reason
    assert info.value.payload() == {"action": "send_package", "reason": info.value.reason}


def test_an_action_on_a_protected_branch_is_refused_in_words() -> None:
    for action in (Action.COMMIT_TO_TASK_BRANCH, Action.INTEGRATE_INTO_RUN_BRANCH):
        with pytest.raises(ActionForbidden) as info:
            authorize(ActionRequest(action, "main"), protected=PROTECTED, sensitive=SENSITIVE)
        assert info.value.reason == "'main' is a protected branch"
