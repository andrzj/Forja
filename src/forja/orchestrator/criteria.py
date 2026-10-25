"""The criteria of a task, and how they reach the stages that work from them."""

from forja.core.artifacts.schemas import CriteriaBody
from forja.orchestrator.ports import RunContext


def criteria_artifact_id(task_id: str) -> str:
    return f"criteria-{task_id}"


def with_criteria(description: str, criteria: CriteriaBody) -> str:
    """The defect and its criteria; the numbers are the ones the test author declares."""
    lines = "\n".join(f"{c.id}. {c.text}" for c in criteria.criteria)
    return f"{description}\n\nCriteria:\n{lines}"


def criteria_of(ctx: RunContext, task_id: str) -> CriteriaBody | None:
    """The criteria the person gave, else the ones the specifier wrote for this task; ``None`` for
    a run with no criteria at all (a refactoring)."""
    fix = ctx.config.fix
    if fix is None:
        return None
    if fix.criteria is not None:
        return fix.criteria
    body = ctx.store.get(criteria_artifact_id(task_id)).body
    assert isinstance(body, CriteriaBody)
    return body
