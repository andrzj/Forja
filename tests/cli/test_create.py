"""``forja criar`` at the door: what it asks, what it refuses, and the scaffold after the yes."""
# ruff: noqa: F811 - the fixtures of test_main are imported to be used here

import subprocess
from pathlib import Path

import pytest

from forja.cli import main as door
from forja.cli import prepare as preparation
from forja.cli.scaffold import ScaffoldError
from forja.cli.settings import Execucao, load_execucao, save_execucao
from forja.orchestrator.config import Objective, RunConfig
from tests.cli.test_main import Talk, environ, git, go, repo  # noqa: F401 - fixtures

pytestmark = pytest.mark.integration

IDEA = "a command that adds two numbers"


@pytest.fixture
def empty(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "novo-proj"
    path.mkdir()
    monkeypatch.chdir(path)
    return path


def saved(tmp_path: Path, **values: str) -> Path:
    path = tmp_path / "execucao.toml"
    fields = {"objetivo": "criar", "descricao": IDEA, "linguagem": "python", "nome": "adder"}
    save_execucao(path, Execucao(**{**fields, **values}))  # type: ignore[arg-type]
    return path


def plan(tmp_path: Path, environ: dict[str, str], talk: Talk, **values: str) -> int:  # noqa: F811
    return go(["--config", str(saved(tmp_path, **values)), "--plano"], talk, environ)


def test_the_plan_of_a_creation_says_what_will_be_made_and_makes_nothing(
    empty: Path,
    environ: dict[str, str],
    tmp_path: Path,  # noqa: F811
) -> None:
    talk = Talk()

    assert plan(tmp_path, environ, talk) == 0

    assert f"Vou criar o projeto adder em {empty}" in talk.text
    assert f"ideia: {IDEA}" in talk.text
    assert "linguagem: python" in talk.text
    assert "`git init`" in talk.text
    assert "o agente que especifica os escreve" in talk.text
    assert list(empty.iterdir()) == []


def test_a_setup_the_language_needs_is_announced(
    empty: Path,
    environ: dict[str, str],
    tmp_path: Path,  # noqa: F811
) -> None:
    talk = Talk()

    plan(tmp_path, environ, talk, linguagem="typescript")

    assert "antes do build, a Forja roda no diretório: npm install" in talk.text


def test_without_a_person_the_language_has_to_be_in_the_file(
    empty: Path,
    environ: dict[str, str],  # noqa: F811
) -> None:
    talk = Talk()

    assert go(["criar", IDEA, "--plano"], talk, environ) == 2

    assert "`linguagem` no execucao.toml" in talk.text
    assert "csharp, go, java, python, typescript" in talk.text


def test_a_person_is_asked_the_language_and_the_name(
    empty: Path,
    environ: dict[str, str],  # noqa: F811
) -> None:
    talk = Talk("4", "meu-proj", interactive=True)

    assert go(["criar", IDEA, "--plano"], talk, environ) == 0

    assert "Em que linguagem?" in talk.text
    assert "projeto meu-proj" in talk.text
    assert "linguagem: python" in talk.text


def test_the_name_of_the_directory_is_offered_as_the_name(
    empty: Path,
    environ: dict[str, str],  # noqa: F811
) -> None:
    talk = Talk("2", interactive=True)

    assert go(["criar", IDEA, "--plano"], talk, environ) == 0

    assert "projeto novo-proj" in talk.text
    assert "linguagem: go" in talk.text


def test_the_idea_is_needed(
    empty: Path,
    environ: dict[str, str],
    tmp_path: Path,  # noqa: F811
) -> None:
    talk = Talk()

    assert plan(tmp_path, environ, talk, descricao="") == 2

    assert "Conte a ideia" in talk.text


def test_the_idea_can_come_from_a_file(
    empty: Path,
    environ: dict[str, str],
    tmp_path: Path,  # noqa: F811
) -> None:
    (tmp_path / "ideia.md").write_text("- adds\n- subtracts\n", encoding="utf-8")
    talk = Talk()

    assert plan(tmp_path, environ, talk, descricao="", arquivo=str(tmp_path / "ideia.md")) == 0

    assert "- adds" in talk.text


@pytest.mark.parametrize("name", ["Meu_Proj", "x" * 41, "-a"])
def test_a_name_that_is_not_a_project_name_is_refused(
    empty: Path,
    environ: dict[str, str],
    tmp_path: Path,
    name: str,  # noqa: F811
) -> None:
    talk = Talk()

    assert plan(tmp_path, environ, talk, nome=name) == 2

    assert "não serve de nome de projeto" in talk.text


def test_a_language_there_is_no_template_for_is_refused(
    empty: Path,
    environ: dict[str, str],
    tmp_path: Path,  # noqa: F811
) -> None:
    talk = Talk()

    assert plan(tmp_path, environ, talk, linguagem="javascript") == 2

    assert "Não sei criar projeto em `javascript`" in talk.text


def test_a_directory_with_files_is_refused(
    empty: Path,
    environ: dict[str, str],
    tmp_path: Path,  # noqa: F811
) -> None:
    (empty / "notes.txt").write_text("mine\n", encoding="utf-8")
    talk = Talk()

    assert plan(tmp_path, environ, talk) == 2

    assert "já tem projeto" in talk.text


def test_a_repository_with_commits_is_refused(
    repo: Path,
    environ: dict[str, str],
    tmp_path: Path,  # noqa: F811
) -> None:
    talk = Talk()

    assert plan(tmp_path, environ, talk) == 2

    assert "já tem projeto" in talk.text


def test_a_repository_with_no_commit_and_nothing_else_is_a_place_for_a_project(
    empty: Path,
    environ: dict[str, str],
    tmp_path: Path,  # noqa: F811
) -> None:
    git(empty, "init", "-q", "-b", "main")

    assert plan(tmp_path, environ, Talk()) == 0


def test_a_repository_with_no_commit_but_with_files_is_refused(
    empty: Path,
    environ: dict[str, str],
    tmp_path: Path,  # noqa: F811
) -> None:
    git(empty, "init", "-q", "-b", "main")
    (empty / "notes.txt").write_text("mine\n", encoding="utf-8")
    talk = Talk()

    assert plan(tmp_path, environ, talk) == 2

    assert "precisa estar vazio" in talk.text and "notes.txt" in talk.text


def test_the_other_commands_point_an_empty_directory_to_criar(
    empty: Path,
    environ: dict[str, str],  # noqa: F811
) -> None:
    talk = Talk()

    assert go(["refatorar", "--plano"], talk, environ) == 2

    assert "forja criar" in talk.text


def test_a_verb_that_is_not_available_says_so(
    empty: Path,
    environ: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,  # noqa: F811
) -> None:
    monkeypatch.setattr(preparation, "AVAILABLE", frozenset({"refatorar"}))
    talk = Talk()

    assert go(["criar"], talk, environ) == 2

    assert "ainda não está disponível" in talk.text


class Started:
    """What ``open_session`` was given."""

    def __init__(self, directory: Path) -> None:
        self.config: RunConfig | None = None
        self.directory = directory


@pytest.fixture
def started(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Started:
    seen = Started(tmp_path / "session")
    seen.directory.mkdir()

    async def open_session(config: RunConfig | None, **_: object) -> object:
        seen.config = config
        return type("Session", (), {"directory": seen.directory})()

    async def run(*_: object) -> int:
        return 0

    monkeypatch.setattr(door, "open_session", open_session)
    monkeypatch.setattr(door, "_run", run)
    return seen


def test_after_the_yes_the_project_is_made_and_the_run_starts_from_its_commit(
    empty: Path,
    environ: dict[str, str],
    tmp_path: Path,
    started: Started,  # noqa: F811
) -> None:
    talk = Talk()

    assert go(["--config", str(saved(tmp_path))], talk, environ) == 0

    assert (empty / "pyproject.toml").is_file()
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=empty, capture_output=True, text=True, check=True
    ).stdout.strip()
    assert started.config is not None
    assert started.config.base_commit == head
    assert started.config.objective is Objective.CREATE
    assert started.config.create is not None
    assert started.config.create.name == "adder"
    assert Path(started.config.repo) == empty
    assert f"Projeto adder criado e comitado ({head[:7]})." in talk.text
    kept = load_execucao(started.directory / "execucao.toml")
    assert (kept.objetivo, kept.linguagem, kept.nome) == ("criar", "python", "adder")


def test_without_the_yes_nothing_is_made(
    empty: Path,
    environ: dict[str, str],
    started: Started,  # noqa: F811
) -> None:
    talk = Talk("4", "meu-proj", "n", interactive=True)

    assert go(["criar", IDEA], talk, environ) == 0

    assert "Cancelado" in talk.text
    assert list(empty.iterdir()) == []
    assert started.config is None


def test_a_scaffold_that_fails_ends_the_start_and_says_why(
    empty: Path,
    environ: dict[str, str],  # noqa: F811
    tmp_path: Path,
    started: Started,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def broken(*_: object) -> str:
        raise ScaffoldError("`npm` não está instalado")

    monkeypatch.setattr(door, "scaffold", broken)
    talk = Talk()

    assert go(["--config", str(saved(tmp_path))], talk, environ) == 2

    assert "`npm` não está instalado" in talk.text
    assert started.config is None
