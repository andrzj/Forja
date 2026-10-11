"""The real Claude Code, called for real. It spends tokens from the user's own login, so it only
runs on request: ``FORJA_LIVE=1 uv run pytest tests/executors/test_live.py``.

It is the proof of life the doctor will run, and the check that the shapes the adapter reads are
the ones the CLI really prints.
"""

import asyncio
import os
from pathlib import Path

import pytest

from forja.core.adapters.common import build_spec
from forja.core.adapters.executor import (
    AGENT_DIR,
    AgentRequest,
    ErrorActivity,
    RolePermissions,
    check_probe,
    find_executors,
)
from forja.core.artifacts.models import Producer
from forja.core.process import ProcessRunner
from forja.executors import ClaudeCodeAdapter
from tests.checks.support import RecordingSink

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(not os.environ.get("FORJA_LIVE"), reason="spends tokens; set FORJA_LIVE=1"),
]


def test_the_real_cli_passes_the_proof_of_life(tmp_path: Path) -> None:
    adapter = ClaudeCodeAdapter()
    found = find_executors(adapter)
    assert found, "claude is not installed or not on the PATH"
    permissions = RolePermissions(can_edit_files=True)
    setup = adapter.permission_setup(Producer.IMPLEMENTER, permissions)
    (tmp_path / AGENT_DIR).mkdir()
    for name, data in setup.files.items():
        (tmp_path / AGENT_DIR / name).write_bytes(data)
    package = tmp_path / AGENT_DIR / "package.md"
    package.write_text(adapter.probe.prompt, encoding="utf-8")
    request = AgentRequest(Producer.IMPLEMENTER, package, tmp_path, permissions)
    plan = adapter.plan_invocation(request, setup, found[0].path)
    runner = ProcessRunner(RecordingSink())

    result = asyncio.run(
        runner.run("probe", build_spec(plan, dict(os.environ), timeout=180), tmp_path / "log.txt")
    )

    lines = [
        line.removeprefix("[out] ")
        for line in (tmp_path / "log.txt").read_text(encoding="utf-8").splitlines()
        if line.startswith("[out] ")
    ]
    activities = [a for a in map(adapter.parse_event, lines) if a is not None]
    errors = [a.message for a in activities if isinstance(a, ErrorActivity)]
    assert not errors, f"the CLI is not ready to be used: {errors[0]}"
    assert result.exit_code == 0
    assert check_probe(adapter.probe, tmp_path, activities) == []
