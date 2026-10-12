"""The door of the Forja: what it says and returns before anything runs, in a real repository."""

import asyncio
import os
import subprocess
import sys
from pathlib import Path

import pytest

from forja.cli import doctor as doctor_module
from forja.cli import main as door
from forja.cli import prepare as preparation
from forja.cli.args import parse
from forja.cli.settings import Perfil, save_perfil
from forja.core.states import ExecutionState
from tests.cli.test_resume import make_run

pytestmark = pytest.mark.integration


class Talk:
    """A console that answers from a list and remembers what was said."""

    def __init__(self, *answers: str, interactive: bool = False) -> None:
        self.interactive = interactive
        self.said: list[str] = []
        self._answers = list(answers)

    def say(self, text: str = "") -> None:
        self.said.append(text)

    def ask(self, question: str, *, default: str = "") -> str:
        return self._answers.pop(0) if self._answers else default

    @property
    def text(self) -> str:
        return "\n".join(self.said)


def git(repo: Path, *args: str) -> None:
    who = {"NAME": "t", "EMAIL": "t@e"}
    env = {**os.environ}
    for part in ("AUTHOR", "COMMITTER"):
        for key, value in who.items():
            env[f"GIT_{part}_{key}"] = value
    subprocess.run(["git", *args], cwd=repo, env=env, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "proj"
    path.mkdir()
    git(path, "init", "-q", "-b", "main")
    (path / "pyproject.toml").write_text('[project]\nname = "p"\nversion = "0"\n', encoding="utf-8")
    git(path, "add", ".")
    git(path, "commit", "-q", "-m", "init")
    monkeypatch.chdir(path)
    return path


@pytest.fixture
def environ(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """A profile that knows where the agent is, and a Forja home of its own."""
    agent = tmp_path / ("claude.exe" if sys.platform == "win32" else "claude")
    agent.write_text("not a real agent", encoding="utf-8")
    agent.chmod(0o755)
    profile = tmp_path / "profile"
    save_perfil(profile, Perfil(cli="claude-code", executaveis={"claude-code": str(agent)}))

    async def proven(*args: object, **kwargs: object) -> str:
        return "2.1.0"

    monkeypatch.setattr(preparation, "prove", proven)
    monkeypatch.setattr(door, "prepare", preparation.prepare)
    env = {**os.environ, "FORJA_CONFIG_HOME": str(profile), "FORJA_HOME": str(tmp_path / "home")}
    monkeypatch.setenv("FORJA_HOME", env["FORJA_HOME"])
    return env


def go(argv: list[str], talk: Talk, environ: dict[str, str]) -> int:
    return asyncio.run(door.amain(parse(argv), talk, environ))


def test_the_plan_shows_what_would_happen_and_changes_nothing(
    repo: Path, environ: dict[str, str]
) -> None:
    talk = Talk()
    code = go(["refatorar", "--plano", "--escopo", "src"], talk, environ)
    assert code == 0
    assert "Vou refatorar proj" in talk.text
    assert "onde: src" in talk.text
    assert "2.000.000 tokens" in talk.text
    assert not (Path(environ["FORJA_HOME"]) / "runs").exists()


def test_unsaved_changes_stop_it_before_anything(repo: Path, environ: dict[str, str]) -> None:
    (repo / "novo.py").write_text("x = 1\n", encoding="utf-8")
    talk = Talk()
    assert go(["refatorar"], talk, environ) == 2
    assert "novo.py" in talk.text
    assert "commit ou stash" in talk.text


def test_a_verb_that_does_not_exist_yet_says_when_it_will(
    repo: Path, environ: dict[str, str]
) -> None:
    talk = Talk()
    assert go(["corrigir"], talk, environ) == 2
    assert "ainda não está disponível" in talk.text
    assert "incremento 3" in talk.text


def test_outside_a_repository_it_says_so(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, environ: dict[str, str]
) -> None:
    empty = tmp_path / "vazio"
    empty.mkdir()
    (empty / "arquivo.txt").write_text("x", encoding="utf-8")
    monkeypatch.chdir(empty)
    talk = Talk()
    assert go(["refatorar"], talk, environ) == 2
    assert "repositório git" in talk.text


def test_an_unfinished_run_blocks_an_unattended_start(repo: Path, environ: dict[str, str]) -> None:
    make_run(Path(environ["FORJA_HOME"]), "r1", repo, to=ExecutionState.PAUSED)
    talk = Talk()
    assert go(["refatorar"], talk, environ) == 2
    assert "execução incompleta" in talk.text


def test_the_doctor_lists_what_is_missing_and_how_to_fix_it(
    repo: Path, environ: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(doctor_module, "installed_clis", lambda *args, **kwargs: [])
    broken = {**environ, "FORJA_CONFIG_HOME": str(repo.parent / "sem-perfil"), "PATH": ""}
    talk = Talk()
    code = go(["doctor"], talk, broken)
    assert code == 1
    assert "[FALTA] CLI claude-code" in talk.text
    assert "->" in talk.text


def test_an_invalid_settings_file_is_named(repo: Path, environ: dict[str, str]) -> None:
    bad = repo.parent / "e.toml"
    bad.write_text("tokenz = 1\n", encoding="utf-8")
    talk = Talk()
    assert go(["--config", str(bad), "refatorar"], talk, environ) == 2
    assert "tokenz" in talk.text


def commit_policy(repo: Path, text: str) -> None:
    (repo / "forja.toml").write_text(text, encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", "policy")


def test_a_forja_toml_with_errors_is_named_before_anything_runs(
    repo: Path, environ: dict[str, str]
) -> None:
    commit_policy(repo, "[checks.tests.commands]" + chr(10) + "nope = 1" + chr(10))
    talk = Talk()

    assert go(["refatorar", "--plano"], talk, environ) == 2
    assert "forja.toml" in talk.text
    assert "nope" in talk.text


def test_the_repositorys_own_policy_is_read_when_it_is_valid(
    repo: Path, environ: dict[str, str]
) -> None:
    commit_policy(
        repo, "[checks.tests.commands]" + chr(10) + 'test = ["python", "-m", "pytest"]' + chr(10)
    )
    talk = Talk()

    assert go(["refatorar", "--plano"], talk, environ) == 0
