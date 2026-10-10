from pydantic import BaseModel, ConfigDict, JsonValue

from forja.core.authorization.actions import (
    BRANCH_ACTIONS,
    CLASSIFICATION,
    Action,
    ActionClass,
    ActionRequest,
)
from forja.core.authorization.branches import ProtectedBranches
from forja.core.isolation.sensitive import SensitivePaths


class Grants(BaseModel):
    """What the user allowed in the preparation. After the confirmation nothing is asked again."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    push_run_branch: bool = False


_GRANT_OF = {Action.PUSH_RUN_BRANCH: "push_run_branch"}


class ActionForbidden(Exception):
    """The action is not allowed. The caller records an ``action_denied`` progress event."""

    def __init__(self, action: Action, reason: str) -> None:
        self.action = action
        self.reason = reason
        super().__init__(f"{action.value} is not allowed: {reason}")

    def payload(self) -> dict[str, JsonValue]:
        return {"action": self.action.value, "reason": self.reason}


def authorize(
    request: ActionRequest,
    grants: Grants,
    *,
    protected: ProtectedBranches,
    sensitive: SensitivePaths,
) -> None:
    """Return normally if the action may happen, raise ``ActionForbidden`` if it may not.

    A forbidden action stays forbidden whatever the grants say. Actions on a branch are refused on
    a protected branch even when automatic or granted. Sending files is refused if any of them is
    sensitive, a second line behind the redaction of the package.
    """
    action = request.action
    if CLASSIFICATION[action] is ActionClass.FORBIDDEN:
        raise ActionForbidden(action, "this action is never allowed")

    if action in BRANCH_ACTIONS:
        if request.branch is None:
            raise ValueError(f"{action.value} needs the branch it touches")
        if protected.is_protected(request.branch):
            raise ActionForbidden(action, f"{request.branch!r} is a protected branch")

    if action is Action.SEND_PACKAGE:
        sensitive_files = [path for path in request.paths if sensitive.matches(path)]
        if sensitive_files:
            raise ActionForbidden(
                action, f"sensitive files cannot be sent: {', '.join(sorted(sensitive_files))}"
            )

    if CLASSIFICATION[action] is ActionClass.NEEDS_GRANT and not getattr(grants, _GRANT_OF[action]):
        raise ActionForbidden(action, "the user did not grant it in the preparation")
