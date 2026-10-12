"""A whole run through ``forja``: a real repository, the real gates, a stand-in for the agent CLI.

Only the agent is faked. Git, ruff, pytest, lizard and the orchestrator are the real ones, so this
is the proof that the pieces fit: the planner finds the complex function, the agent's work is
measured and committed to a branch, and the person's branch is left alone.
"""

import asyncio
import json
import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from forja.cli import main as door
from forja.cli import prepare as preparation
from forja.cli import session as session_module
from forja.cli.args import parse
from forja.cli.settings import Execucao, save_execucao
from tests.cli.test_main import Talk, git
from tests.executors.test_agent_runner import FakeCli

pytestmark = [pytest.mark.integration, pytest.mark.slow]

CASES = 18
NL = chr(10)
BEFORE = (
    "def label(n):" + NL
    + "".join(
        f"    {'if' if i == 0 else 'elif'} n == {i}:" + NL + f'        return "n{i}"' + NL
        for i in range(CASES)
    )
    + '    return "other"' + NL
)  # fmt: skip
AFTER = (
    "NAMES = {" + NL
    + "".join(f'    {i}: "n{i}",' + NL for i in range(CASES))
    + "}" + NL + NL + NL
    + "def label(n):" + NL + '    return NAMES.get(n, "other")' + NL
)  # fmt: skip
TEST = (
    "from pkg.mod import label\n\n\n"
    "def test_label():\n"
    f"    assert [label(i) for i in range({CASES + 2})] == "
    f"[f'n{{i}}' for i in range({CASES})] + ['other', 'other']\n"
)
DECLARED = {
    "actions": [
        {
            "summary": "a lookup table instead of a chain of comparisons",
            "reason": "the complexity was the number of branches",
            "files": [{"path": "src/pkg/mod.py", "change": "modified"}],
        }
    ]
}
USAGE = {"type": "result", "is_error": False, "usage": {"input_tokens": 900, "output_tokens": 100}}


def make_repo(root: Path) -> Path:
    repo = root / "proj"
    (repo / "src" / "pkg").mkdir(parents=True)
    (repo / "tests").mkdir()
    (repo / "pyproject.toml").write_text(
        '[project]\nname = "pkg"\nversion = "0"\n\n[tool.pytest.ini_options]\n'
        'pythonpath = ["src"]\n',
        encoding="utf-8",
    )
    (repo / "src" / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (repo / "src" / "pkg" / "mod.py").write_text(BEFORE, encoding="utf-8", newline="\n")
    (repo / "tests" / "test_mod.py").write_text(TEST, encoding="utf-8", newline="\n")
    git(repo, "init", "-q", "-b", "main")
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", "init")
    return repo


def run(*argv: str, cwd: Path, **kept: str) -> str:
    done = subprocess.run(
        ["git", *argv], cwd=cwd, capture_output=True, text=True, check=True, encoding="utf-8"
    )
    return done.stdout.strip()


WRONG = AFTER.replace('NAMES.get(n, "other")', '"always"')


class Outcome:
    def __init__(self, code: int, text: str, repo: Path, before: str) -> None:
        self.code, self.text, self.repo, self.before = code, text, repo, before

    def delivered(self, path: str = "src/pkg/mod.py") -> str:
        branches = [
            b.strip(" *+")
            for b in run("branch", "--list", "forja-run/*", cwd=self.repo).splitlines()
        ]
        assert len(branches) == 1, self.text
        return run("show", f"{branches[0]}:{path}", cwd=self.repo)


class Armed:
    """Everything a run needs, set up: the repository, the stand-in agent and the answers file."""

    def __init__(self, repo: Path, before: str, answers: Path, script: Path) -> None:
        self.repo, self.before, self.answers, self.script = repo, before, answers, script


def arm(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    script: dict[str, Any],
    repo: Path | None = None,
) -> Armed:
    """Put the stand-in agent, a stand-in gitleaks and the profile in place around a repository."""
    repo = repo or make_repo(tmp_path)
    monkeypatch.chdir(repo)
    before = run("rev-parse", "HEAD", cwd=repo)
    script_path = tmp_path / "script.json"
    script_path.write_text(
        json.dumps({"record": str(tmp_path / "record.json"), **script}), encoding="utf-8"
    )

    async def proven(*args: object, **kwargs: object) -> str:
        return "2.1.0"

    agent = tmp_path / ("claude.exe" if sys.platform == "win32" else "claude")
    agent.write_text("stand-in", encoding="utf-8")
    agent.chmod(0o755)
    leaks = tmp_path / ("gitleaks.cmd" if sys.platform == "win32" else "gitleaks")
    nl = chr(10)
    leaks.write_text(
        "@exit /b 0" + nl if sys.platform == "win32" else "#!/bin/sh" + nl + "exit 0" + nl,
        encoding="utf-8",
    )
    leaks.chmod(0o755)  # a stand-in that finds nothing: gitleaks itself is not on every machine
    monkeypatch.setattr(session_module, "missing_tool", lambda name: str(leaks))
    monkeypatch.setattr(preparation, "prove", proven)
    monkeypatch.setattr(session_module, "ClaudeCodeAdapter", lambda: FakeCli(script_path))
    monkeypatch.setattr(session_module, "repo_python", lambda _repo: (sys.executable,))
    monkeypatch.setenv("FORJA_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("FORJA_CONFIG_HOME", str(tmp_path / "profile"))
    answers = tmp_path / "execucao.toml"
    save_execucao(answers, Execucao(cli="claude-code", executavel=str(agent), tokens=500_000))
    return Armed(repo, before, answers, script_path)


def forja(armed: Armed, *argv: str, talk: Talk | None = None) -> tuple[int, Talk]:
    """One invocation of ``forja`` in the armed repository."""
    talk = talk or Talk()
    code = asyncio.run(door.amain(parse(list(argv)), talk, dict(os.environ)))
    return code, talk


def whole_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    written: str,
    extra: Callable[[Path], dict[str, Any]] | None = None,
) -> Outcome:
    """Run ``forja refatorar`` unattended, the stand-in agent writing ``written``."""
    repo = make_repo(tmp_path)
    script = {
        "writes": {"src/pkg/mod.py": written},
        "saida": DECLARED,
        "lines": [json.dumps(USAGE)],
        **(extra(repo) if extra else {}),
    }
    armed = arm(tmp_path, monkeypatch, script, repo)
    code, talk = forja(armed, "--config", str(armed.answers), "refatorar")
    return Outcome(code, capsys.readouterr().out + talk.text, repo, armed.before)


def test_a_whole_run_delivers_a_branch_and_leaves_the_users_branch_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    result = whole_run(tmp_path, monkeypatch, capsys, AFTER)

    assert result.code == 0, result.text
    assert "forja-run/" in result.text
    assert run("rev-parse", "HEAD", cwd=result.repo) == result.before, "the user's branch moved"
    assert run("status", "--porcelain", cwd=result.repo) == ""
    assert "NAMES" in result.delivered()
    assert "Nenhuma tarefa foi integrada" not in result.text
    assert "bloqueada" not in result.text


def test_work_that_changes_the_behaviour_never_reaches_the_branch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    result = whole_run(tmp_path, monkeypatch, capsys, WRONG)

    assert result.code == 4, result.text
    assert "always" not in result.delivered(), result.text
    assert "0 de 1 tarefa(s) integrada(s); 1 bloqueada(s)" in result.text
    assert "Nenhuma tarefa foi integrada" in result.text
    assert "0 integrada(s), 1 bloqueada(s)" in result.text  # the last line of the screen
    assert run("rev-parse", "HEAD", cwd=result.repo) == result.before
    assert run("status", "--porcelain", cwd=result.repo) == ""
