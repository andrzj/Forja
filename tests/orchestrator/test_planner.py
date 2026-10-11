"""The planner: the worst functions first, within the budget, with the limits of the budget."""

import asyncio
from pathlib import Path

from forja.orchestrator.config import Budget
from forja.orchestrator.planner import ComplexityPlanner
from forja.orchestrator.ports import Baseline, PlannedTask

FOUND = {
    ("src/a.py", "calm"): 3,
    ("src/a.py", "tangled"): 22,
    ("src/b.py", "worse"): 40,
    ("src/b.py", "limit"): 15,
    ("src/c.py", "tie_b"): 20,
    ("src/c.py", "tie_a"): 20,
}


def plan(budget: Budget = Budget(), max_ccn: int = 15) -> list[PlannedTask]:  # noqa: B008
    async def functions(worktree: Path) -> dict[tuple[str, str], int]:
        return FOUND

    planner = ComplexityPlanner(functions, max_ccn)
    return list(asyncio.run(planner.plan(Path("."), Baseline(True), budget)))


def test_the_most_complex_functions_come_first_and_only_those_above_the_limit() -> None:
    tasks = plan()

    assert [t.intent for t in tasks] == [
        "reduce the complexity of worse in src/b.py",
        "reduce the complexity of tangled in src/a.py",
        "reduce the complexity of tie_a in src/c.py",
        "reduce the complexity of tie_b in src/c.py",
    ]


def test_a_function_at_the_limit_is_not_above_it() -> None:
    assert all("limit" not in t.intent for t in plan())
    assert any("limit" in t.intent for t in plan(max_ccn=14))


def test_each_task_may_touch_its_file_within_the_budgets_limits() -> None:
    task = plan(Budget(files_per_task=2, lines_per_task=50))[0]

    assert task.scope == ("src/b.py",)
    assert (task.max_files, task.max_lines) == (2, 50)


def test_the_plan_has_no_more_tasks_than_the_budget_allows() -> None:
    assert len(plan(Budget(tasks=2))) == 2
    assert len(plan(Budget(tasks=1))) == 1


def test_nothing_to_do_is_an_empty_plan() -> None:
    assert plan(max_ccn=100) == []
