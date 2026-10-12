"""Acceptance: an agent that tries to use git fails, or is caught and its attempt refused."""

import json
import os
from pathlib import Path

import pytest

from tests.cli.test_e2e import AFTER, run, whole_run

pytestmark = [pytest.mark.integration, pytest.mark.slow]


def reasons(home: Path) -> list[str]:
    found = []
    for log in (home / "runs").glob("*/events.jsonl"):
        for line in log.read_text(encoding="utf-8").splitlines():
            event = json.loads(line)
            reason = event.get("payload", {}).get("reason", "")
            if event.get("type") == "transition" and event.get("level") == "attempt" and reason:
                found.append(str(reason))
    return found


def test_git_does_not_work_inside_the_agents_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    ran = tmp_path / "ran.json"

    def commands(repo: Path) -> dict[str, object]:
        return {
            "ran": str(ran),
            "run": [
                {"cmd": ["git", "status"]},
                {"cmd": ["git", "log", "-1"]},
                {"cmd": ["git", "-C", str(repo), "status"]},  # the real repository, by path
            ],
        }

    result = whole_run(tmp_path, monkeypatch, capsys, AFTER, commands)

    attempts = json.loads(ran.read_text(encoding="utf-8"))
    assert [item["code"] != 0 for item in attempts] == [True, True, True], attempts
    assert all("not a git repository" in item["out"] for item in attempts), attempts
    assert run("status", "--porcelain", cwd=result.repo) == ""
    assert run("rev-parse", "HEAD", cwd=result.repo) == result.before


def test_an_agent_that_reaches_the_real_repository_anyway_is_caught(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def sneaky(repo: Path) -> dict[str, object]:
        git_dir = str(repo / ".git")
        return {
            "ran": str(tmp_path / "ran.json"),
            "run": [
                {"cmd": ["git", f"--git-dir={git_dir}", "update-ref", "refs/heads/evil", "HEAD"]}
            ],
        }

    result = whole_run(tmp_path, monkeypatch, capsys, AFTER, sneaky)

    found = reasons(Path(os.environ["FORJA_HOME"]))
    assert any("git" in reason.lower() or "ref" in reason.lower() for reason in found), found
    assert result.code == 3, result.text  # stopped with everything saved, not delivered
    assert "git changed while the agent ran" in result.text or "paus" in result.text.lower()
    assert "NAMES" not in result.delivered()
