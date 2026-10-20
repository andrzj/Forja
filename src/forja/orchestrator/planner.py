"""The plan of a refactoring run, made without a model: the most complex functions first.

A model that picks its own work picks what is interesting, not what is worst. The measure decides,
the model only does the task it is given.
"""

from collections.abc import Awaitable, Callable, Mapping, Sequence
from pathlib import Path

from forja.checks.complexity import DEFAULT_MAX_CCN
from forja.core.artifacts.models import Producer
from forja.orchestrator.config import Budget, FixRequest
from forja.orchestrator.ports import TEST_ROOT, Baseline, PlannedTask

# (file, function) -> cyclomatic complexity
Functions = Callable[[Path], Awaitable[Mapping[tuple[str, str], int]]]


class ComplexityPlanner:
    def __init__(self, functions: Functions, max_ccn: int = DEFAULT_MAX_CCN) -> None:
        self._functions = functions
        self._max_ccn = max_ccn

    async def plan(
        self, worktree: Path, baseline: Baseline, budget: Budget
    ) -> Sequence[PlannedTask]:
        found = await self._functions(worktree)
        worst = sorted(
            ((ccn, file, name) for (file, name), ccn in found.items() if ccn > self._max_ccn),
            key=lambda item: (-item[0], item[1], item[2]),
        )
        return [
            PlannedTask(
                intent=f"reduce the complexity of {name} in {file}",
                scope=(file,),
                max_files=budget.files_per_task,
                max_lines=budget.lines_per_task,
            )
            for _, file, name in worst[: budget.tasks]
        ]


class FixPlanner:
    """The plan of a fix run: one task, the tests first and then the code that makes them pass."""

    def __init__(self, fix: FixRequest, scope: Sequence[str], test_root: str = TEST_ROOT) -> None:
        self._fix = fix
        self._scope = tuple(scope)
        self._test_root = test_root

    def _intent(self) -> str:
        """The defect and its criteria; the numbers are the ones the test author declares."""
        criteria = "\n".join(f"{c.id}. {c.text}" for c in self._fix.criteria.criteria)
        return f"{self._fix.description}\n\nCriteria:\n{criteria}"

    async def plan(
        self, worktree: Path, baseline: Baseline, budget: Budget
    ) -> Sequence[PlannedTask]:
        return [
            PlannedTask(
                intent=self._intent(),
                scope=self._scope,
                max_files=budget.files_per_task,
                max_lines=budget.lines_per_task,
                stages=(Producer.TEST_AUTHOR, Producer.IMPLEMENTER),
                test_root=self._test_root,
            )
        ]
