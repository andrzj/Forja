"""The real Claude Code as the test author, on a planted defect. It spends tokens from the user's
own login, so it only runs on request:
``FORJA_LIVE=1 uv run pytest tests/executors/test_live_fix.py``.

What it proves: the package of the test author is enough for the real CLI to write tests that the
red gate accepts (each one fails on the defect), declared in the shape the runner reads.
"""

import asyncio
import json
import os
import shutil
from pathlib import Path

import pytest

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
from forja.orchestrator.ports import AttemptContext, Baseline, TaskInfo
from tests.checks.support import RUN, RecordingSink
from tests.checks.test_units import data, tools
from tests.core.events.support import FakeClock
from tests.executors.test_agent_runner import go, settle

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(not os.environ.get("FORJA_LIVE"), reason="spends tokens; set FORJA_LIVE=1"),
]

DEFECT = Path(__file__).resolve().parents[2] / "scripts" / "medicao" / "defeitos" / "pager"


def test_the_real_cli_writes_tests_that_the_red_gate_accepts(tmp_path: Path) -> None:
    adapter = ClaudeCodeAdapter()
    found = find_executors(adapter)
    assert found, "claude is not installed or not on the PATH"
    worktree = tmp_path / "wt" / "t1-ta1"
    shutil.copytree(DEFECT / "repo", worktree)
    (worktree / ".git").mkdir()
    (worktree / ".git" / "HEAD").write_text("ref: refs/heads/x", encoding="utf-8")
    log = EventLog.open(tmp_path / "events.jsonl", RUN, clock=FakeClock())
    log.append_transition(Level.EXECUTION, RUN, None, ExecutionState.PREPARING)
    fix = FixRequest.model_validate(
        {
            "description": (DEFECT / "descricao.txt").read_text(encoding="utf-8"),
            "criteria": json.loads((DEFECT / "criterios.json").read_text(encoding="utf-8")),
        }
    )
    planned = asyncio.run(FixPlanner(fix, ("src/pager",)).plan(worktree, Baseline(True), Budget()))[
        0
    ]
    task = TaskInfo(
        "t1", "t1-t", planned.intent, planned.scope, planned.max_files, planned.max_lines,
        Producer.TEST_AUTHOR, planned.test_root,
    )  # fmt: skip
    ctx = AttemptContext(task, "t1-ta1", worktree, None)
    runner = ExecutorAgentRunner(
        adapter,
        found[0].path,
        dict(os.environ),
        log,
        role=Producer.TEST_AUTHOR,
        permissions=RolePermissions(can_edit_files=True),
    )

    go(settle(runner.prepare_workcopy(ctx)))
    result = go(runner.call(ctx, "call_agent_cli:t1-ta1", RecordingSink()))
    assert result.error is None, result.error
    go(settle(runner.apply_diff(ctx)))

    declared = runner.declared_tests(ctx)
    criteria = frozenset(int(c.id) for c in fix.criteria.criteria)
    python = PythonAdapter()
    check = RedGreenCheck(
        tools(log, worktree),
        python,
        worktree,
        lambda path: python.classify(path) or FileClass.OTHER,
        criteria,
        declared,
    )
    assert asyncio.run(check.evaluate(data())) == Approved()
