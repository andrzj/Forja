"""The real Claude Code in both roles of a fix, on a planted defect. It spends tokens from the
user's own login, so it only runs on request:
``FORJA_LIVE=1 uv run pytest tests/executors/test_live_fix.py``.

What it proves: the package of the test author is enough for the real CLI to write tests that the
red gate accepts (each one fails on the defect), declared in the shape the runner reads; and the
package of the implementer is enough for it to turn those tests green without touching them.

Each call of the agent may use at most ``TOKEN_CEILING`` tokens (the owner's ceiling, 13/10); the
test fails if one goes over. The runner has no way to stop a call that is running, so the ceiling
is checked when the call ends. The tokens of every call are printed (``pytest -s``).
"""

import asyncio
import json
import os
import shutil
from pathlib import Path

import pytest

from forja.checks.build_and_tests import TestsCheck
from forja.checks.changes import Changes
from forja.checks.freeze import FreezeCheck, tree_digest
from forja.checks.red_green import RedGreenCheck
from forja.core.adapters import FileClass
from forja.core.adapters.executor import RolePermissions, find_executors
from forja.core.artifacts.models import Producer
from forja.core.events import EventLog
from forja.core.gates import Approved
from forja.core.states import ExecutionState, Level
from forja.executors import ClaudeCodeAdapter
from forja.languages.python import PythonAdapter
from forja.orchestrator.agent_runner import ExecutorAgentRunner
from forja.orchestrator.config import Budget, FixRequest
from forja.orchestrator.planner import FixPlanner
from forja.orchestrator.ports import AttemptContext, Baseline, PlannedTask, TaskInfo
from tests.checks.support import RUN, RecordingSink
from tests.checks.test_units import data, tools
from tests.core.events.support import FakeClock
from tests.executors.test_agent_runner import go, settle

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(not os.environ.get("FORJA_LIVE"), reason="spends tokens; set FORJA_LIVE=1"),
]

DEFECTS = Path(__file__).resolve().parents[2] / "scripts" / "medicao" / "defeitos"
TOKEN_CEILING = 200_000


def tokens_used(log_path: Path) -> int:
    """The sum of the usage the log recorded, in whatever event it sits."""

    def walk(node: object) -> int:
        if isinstance(node, dict):
            own = (
                int(node.get("input", 0)) + int(node.get("output", 0))
                if node.get("type") == "usage"
                else 0
            )
            return own + sum(walk(value) for value in node.values())
        if isinstance(node, list):
            return sum(walk(item) for item in node)
        return 0

    return sum(
        walk(json.loads(line))
        for line in log_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    )


def stage(planned: PlannedTask, role: Producer, frozen_digest: str = "") -> tuple[TaskInfo, str]:
    """The task as one of its stages sees it, and the id of that stage's first attempt."""
    author = role is Producer.TEST_AUTHOR
    info = TaskInfo(
        "t1",
        "t1-t" if author else "t1-s",
        planned.intent,
        planned.scope,
        planned.max_files,
        planned.max_lines,
        role,
        planned.test_root,
        "t1-ta" if author else "t1-a",
        frozen_digest,
    )
    return info, f"{info.attempt_prefix}1"


@pytest.mark.parametrize(("name", "scope"), [("pager", "src/pager"), ("money", "src/money")])
def test_the_real_cli_writes_the_tests_and_then_fixes_the_defect(
    name: str, scope: str, tmp_path: Path
) -> None:
    defect = DEFECTS / name
    adapter = ClaudeCodeAdapter()
    found = find_executors(adapter)
    assert found, "claude is not installed or not on the PATH"
    worktree = tmp_path / "wt" / "t1-ta1"
    shutil.copytree(defect / "repo", worktree)
    (worktree / ".git").mkdir()
    (worktree / ".git" / "HEAD").write_text("ref: refs/heads/x", encoding="utf-8")
    log_path = tmp_path / "events.jsonl"
    log = EventLog.open(log_path, RUN, clock=FakeClock())
    log.append_transition(Level.EXECUTION, RUN, None, ExecutionState.PREPARING)
    fix = FixRequest.model_validate(
        {
            "description": (defect / "descricao.txt").read_text(encoding="utf-8"),
            "criteria": json.loads((defect / "criterios.json").read_text(encoding="utf-8")),
        }
    )
    planned = asyncio.run(FixPlanner(fix, (scope,)).plan(worktree, Baseline(True), Budget()))[0]
    python = PythonAdapter()

    def runner(role: Producer) -> ExecutorAgentRunner:
        return ExecutorAgentRunner(
            adapter,
            found[0].path,
            dict(os.environ),
            log,
            role=role,
            permissions=RolePermissions(can_edit_files=True),
        )

    def call(
        role: Producer, info: TaskInfo, attempt: str
    ) -> tuple[ExecutorAgentRunner, AttemptContext]:
        ctx = AttemptContext(info, attempt, worktree, None)
        agent = runner(role)
        before = tokens_used(log_path)
        go(settle(agent.prepare_workcopy(ctx)))
        result = go(agent.call(ctx, f"call_agent_cli:{attempt}", RecordingSink()))
        assert result.error is None, result.error
        go(settle(agent.apply_diff(ctx)))
        spent = tokens_used(log_path) - before
        print(f"[live] {name} {role.value}: {spent} tokens")  # noqa: T201
        assert spent <= TOKEN_CEILING, f"{role.value} spent {spent} tokens, over the ceiling"
        return agent, ctx

    # stage 1: the test author writes tests that fail on the defect
    info, attempt = stage(planned, Producer.TEST_AUTHOR)
    author, ctx = call(Producer.TEST_AUTHOR, info, attempt)
    criteria = frozenset(int(c.id) for c in fix.criteria.criteria)
    red = RedGreenCheck(
        tools(log, tmp_path),
        (python,),
        worktree,
        lambda path: python.classify(path) or FileClass.OTHER,
        criteria,
        author.declared_tests(ctx),
    )
    assert asyncio.run(red.evaluate(data())) == Approved()

    # stage 2: the implementer makes them pass and leaves them as they are
    frozen = tree_digest(worktree, planned.test_root)
    info, attempt = stage(planned, Producer.IMPLEMENTER, frozen)
    call(Producer.IMPLEMENTER, info, attempt)
    freeze = FreezeCheck(worktree, Changes((), 0, ()), planned.test_root, frozen)
    assert asyncio.run(freeze.evaluate(data())) == Approved()
    green = TestsCheck(tools(log, tmp_path), (python,), worktree)
    assert asyncio.run(green.evaluate(data())) == Approved()
