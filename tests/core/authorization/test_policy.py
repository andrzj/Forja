"""The authorization table of contract 3, written out by hand and checked action by action."""

import itertools

import pytest

from forja.core.authorization import (
    CLASSIFICATION,
    Action,
    ActionClass,
    ActionForbidden,
    ActionRequest,
    Grants,
    ProtectedBranches,
    authorize,
)
from forja.core.isolation import SensitivePaths

PROTECTED = ProtectedBranches(frozenset({"main"}))
SENSITIVE = SensitivePaths.with_defaults(case_insensitive=False)

# Transcribed from the spec: automatic, decided in the preparation, forbidden.
SPEC = {
    "read_repository": "automatic",
    "create_worktree": "automatic",
    "remove_worktree": "automatic",
    "run_adapter": "automatic",
    "send_package": "automatic",
    "commit_to_task_branch": "automatic",
    "integrate_into_run_branch": "automatic",
    "push_run_branch": "needs_grant",
    "push_protected_branch": "forbidden",
    "merge_into_protected_branch": "forbidden",
    "delete_branch": "forbidden",
    "rewrite_published_history": "forbidden",
    "send_sensitive_file": "forbidden",
    "expose_secrets_to_agent": "forbidden",
}
BRANCH_ACTIONS = {"commit_to_task_branch", "integrate_into_run_branch", "push_run_branch"}


def test_every_action_is_classified_as_the_spec_says() -> None:
    assert {a.value for a in Action} == set(SPEC)
    assert {a.value: c.value for a, c in CLASSIFICATION.items()} == SPEC


def request(action: Action, *, protected: bool = False, sensitive: bool = False) -> ActionRequest:
    branch = ("main" if protected else "forja/run1/t1") if action.value in BRANCH_ACTIONS else None
    paths = ("src/a.py", ".env") if sensitive else ("src/a.py", "README.md")
    return ActionRequest(action, branch, paths if action is Action.SEND_PACKAGE else ())


def expected(action: Action, *, granted: bool, protected: bool, sensitive: bool) -> bool:
    if SPEC[action.value] == "forbidden":
        return False
    if action.value in BRANCH_ACTIONS and protected:
        return False
    if action is Action.PUSH_RUN_BRANCH and not granted:
        return False
    return not (action is Action.SEND_PACKAGE and sensitive)


CASES = [
    pytest.param(a, g, p, s, id=f"{a.value}|grant={g}|protected={p}|sensitive={s}")
    for a, g, p, s in itertools.product(Action, (False, True), (False, True), (False, True))
]


@pytest.mark.parametrize(("action", "granted", "protected", "sensitive"), CASES)
def test_every_combination_is_decided_as_the_spec_says(
    action: Action, granted: bool, protected: bool, sensitive: bool
) -> None:
    grants = Grants(push_run_branch=granted)

    def call() -> None:
        authorize(
            request(action, protected=protected, sensitive=sensitive),
            grants,
            protected=PROTECTED,
            sensitive=SENSITIVE,
        )

    if expected(action, granted=granted, protected=protected, sensitive=sensitive):
        call()
    else:
        with pytest.raises(ActionForbidden) as info:
            call()
        assert info.value.action is action


def test_a_forbidden_action_stays_forbidden_whatever_is_granted() -> None:
    everything = Grants(push_run_branch=True)
    for action in (a for a in Action if CLASSIFICATION[a] is ActionClass.FORBIDDEN):
        with pytest.raises(ActionForbidden, match="never allowed"):
            authorize(ActionRequest(action), everything, protected=PROTECTED, sensitive=SENSITIVE)


def test_grants_default_to_nothing() -> None:
    assert Grants().push_run_branch is False
    with pytest.raises(ActionForbidden, match="did not grant"):
        authorize(
            ActionRequest(Action.PUSH_RUN_BRANCH, "forja/run1"),
            Grants(),
            protected=PROTECTED,
            sensitive=SENSITIVE,
        )


def test_a_push_is_refused_on_a_protected_branch_even_when_granted() -> None:
    with pytest.raises(ActionForbidden, match="protected branch"):
        authorize(
            ActionRequest(Action.PUSH_RUN_BRANCH, "main"),
            Grants(push_run_branch=True),
            protected=PROTECTED,
            sensitive=SENSITIVE,
        )


def test_an_action_on_a_branch_must_say_which_branch() -> None:
    with pytest.raises(ValueError, match="needs the branch"):
        authorize(
            ActionRequest(Action.COMMIT_TO_TASK_BRANCH),
            Grants(),
            protected=PROTECTED,
            sensitive=SENSITIVE,
        )


def test_the_denial_names_the_sensitive_files_and_becomes_a_loggable_payload() -> None:
    with pytest.raises(ActionForbidden) as info:
        authorize(
            ActionRequest(Action.SEND_PACKAGE, paths=("src/a.py", "config/.env", "keys/x.pem")),
            Grants(),
            protected=PROTECTED,
            sensitive=SENSITIVE,
        )

    assert "config/.env, keys/x.pem" in info.value.reason
    assert info.value.payload() == {"action": "send_package", "reason": info.value.reason}


def test_grants_reject_unknown_fields() -> None:
    with pytest.raises(ValueError):
        Grants.model_validate({"push_run_branch": True, "force_push": True})
