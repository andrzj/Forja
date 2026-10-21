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
from forja.cli.settings import Execucao, Perfil, load_perfil, save_perfil
from forja.core.states import ExecutionState
from forja.executors import KNOWN_CLIS, ClaudeCodeAdapter
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
    assert go(["criar"], talk, environ) == 2
    assert "ainda não está disponível" in talk.text
    assert "incremento 6" in talk.text


CRITERIA = (
    '{"criteria": [{"id": 1, "text": "page 1 is the first items", "level": "unit",'
    ' "origin": "task description"}, {"id": 2, "text": "all pages are the list",'
    ' "level": "unit", "origin": "task description"}]}'
)


def test_fixing_needs_a_description(repo: Path, environ: dict[str, str]) -> None:
    talk = Talk()
    assert go(["corrigir", "--plano"], talk, environ) == 2
    assert "Descreva o erro" in talk.text


def test_fixing_needs_criteria(repo: Path, environ: dict[str, str]) -> None:
    talk = Talk()
    assert go(["corrigir", "page 1 is wrong", "--plano"], talk, environ) == 2
    assert "Faltam os critérios" in talk.text
    assert "--criterios" in talk.text


def test_criteria_that_do_not_fit_the_contract_are_named(
    repo: Path, tmp_path: Path, environ: dict[str, str]
) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text('{"criteria": [{"id": 0, "text": "x", "level": "unit", "origin": "o"}]}')
    talk = Talk()
    assert go(["corrigir", "x is wrong", "--criterios", str(bad), "--plano"], talk, environ) == 2
    assert "não servem" in talk.text
    assert "criteria.0.id" in talk.text


def test_criteria_that_are_not_json_are_named(
    repo: Path, tmp_path: Path, environ: dict[str, str]
) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("not json")
    talk = Talk()
    assert go(["corrigir", "x is wrong", "--criterios", str(bad), "--plano"], talk, environ) == 2
    assert "não servem" in talk.text


def test_a_missing_criteria_file_is_named(
    repo: Path, tmp_path: Path, environ: dict[str, str]
) -> None:
    missing = tmp_path / "nope.json"
    talk = Talk()
    assert go(["corrigir", "x", "--criterios", str(missing), "--plano"], talk, environ) == 2
    assert "Não consegui ler os critérios" in talk.text


def test_the_fix_plan_shows_the_defect_and_the_criteria(
    repo: Path, tmp_path: Path, environ: dict[str, str]
) -> None:
    criteria = tmp_path / "c.json"
    criteria.write_text(CRITERIA, encoding="utf-8")
    talk = Talk()
    argv = ["corrigir", "page 1 is wrong", "--criterios", str(criteria), "--plano"]
    assert go(argv, talk, environ) == 0
    assert "Vou corrigir proj" in talk.text
    assert "erro: page 1 is wrong" in talk.text
    assert "critérios: 2" in talk.text


def test_a_test_author_cli_that_is_not_known_is_refused(
    repo: Path, tmp_path: Path, environ: dict[str, str]
) -> None:
    criteria = tmp_path / "c.json"
    criteria.write_text(CRITERIA, encoding="utf-8")
    talk = Talk()
    argv = ["corrigir", "x", "--criterios", str(criteria), "--cli-testes", "nenhuma", "--plano"]
    assert go(argv, talk, environ) == 2
    assert "Não conheço a CLI `nenhuma`" in talk.text


def test_each_role_of_a_fix_can_run_on_its_own_cli(
    repo: Path, tmp_path: Path, environ: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(KNOWN_CLIS, "outra-cli", ClaudeCodeAdapter)
    agent = next(iter(load_perfil(Path(environ["FORJA_CONFIG_HOME"])).executaveis.values()))
    save_perfil(
        Path(environ["FORJA_CONFIG_HOME"]),
        Perfil(cli="claude-code", executaveis={"claude-code": agent, "outra-cli": agent}),
    )
    criteria = tmp_path / "c.json"
    criteria.write_text(CRITERIA, encoding="utf-8")
    talk = Talk()
    argv = ["corrigir", "x", "--criterios", str(criteria), "--cli-testes", "outra-cli", "--plano"]
    assert go(argv, talk, environ) == 0
    assert "agente que escreve os testes: outra-cli 2.1.0" in talk.text
    assert "agente que implementa: claude-code 2.1.0" in talk.text


def test_the_model_is_the_clis_own_unless_one_is_asked_for_per_role(
    repo: Path, tmp_path: Path, environ: dict[str, str]
) -> None:
    criteria = tmp_path / "c.json"
    criteria.write_text(CRITERIA, encoding="utf-8")
    plain = Talk()
    assert go(["corrigir", "x", "--criterios", str(criteria), "--plano"], plain, environ) == 0
    assert "modelo" not in plain.text

    chosen = Talk()
    argv = ["corrigir", "x", "--criterios", str(criteria), "--modelo", "m1"]
    argv += ["--modelo-testes", "m2", "--plano"]
    assert go(argv, chosen, environ) == 0
    assert "agente que escreve os testes: claude-code 2.1.0, modelo m2" in chosen.text
    assert "agente que implementa: claude-code 2.1.0, modelo m1" in chosen.text


def test_the_description_file_brings_its_criteria_along(
    repo: Path, tmp_path: Path, environ: dict[str, str]
) -> None:
    (tmp_path / "criterios.json").write_text(CRITERIA, encoding="utf-8")
    (tmp_path / "erro.txt").write_text("  page 1 is wrong" + chr(10), encoding="utf-8")
    talk = Talk()
    assert go(["corrigir", "-f", str(tmp_path / "erro.txt"), "--plano"], talk, environ) == 0
    assert "erro: page 1 is wrong" in talk.text


def test_a_saved_fix_is_read_back_from_execucao(tmp_path: Path) -> None:
    criteria = tmp_path / "c.json"
    criteria.write_text(CRITERIA, encoding="utf-8")
    saved = Execucao(objetivo="corrigir", descricao="page 1 is wrong", criterios=str(criteria))
    request, description, where = preparation.read_fix(parse(["corrigir"]), saved)
    assert request.description == description == "page 1 is wrong"
    assert [c.id for c in request.criteria.criteria] == [1, 2]
    assert Path(where) == criteria.resolve()


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


def test_what_the_repositorys_policy_changes_is_told_before_the_confirmation(
    repo: Path, environ: dict[str, str]
) -> None:
    commit_policy(
        repo,
        "[checks.secrets]" + chr(10) + 'mode = "observation"' + chr(10) + chr(10)
        + "[checks.tests.commands]" + chr(10) + 'test = ["python", "-m", "pytest"]' + chr(10),
    )  # fmt: skip
    talk = Talk()

    assert go(["refatorar", "--plano"], talk, environ) == 0
    assert "forja.toml do repositório muda o padrão" in talk.text
    assert "secrets: modo ou política diferente do padrão (observation" in talk.text
    assert "tests: roda no lugar do padrão (test): python -m pytest" in talk.text


def test_a_repository_without_a_policy_file_says_nothing_about_one(
    repo: Path, environ: dict[str, str]
) -> None:
    talk = Talk()

    assert go(["refatorar", "--plano"], talk, environ) == 0
    assert "forja.toml" not in talk.text


def test_everything_a_policy_can_loosen_is_listed_with_its_values(
    repo: Path, environ: dict[str, str]
) -> None:
    commit_policy(
        repo,
        "[checks.complexity.thresholds.python]" + chr(10) + "max_ccn = 40" + chr(10) + chr(10)
        + "[redaction]" + chr(10) + 'pii = ["email"]' + chr(10) + "entropy_threshold = 4.0"
        + chr(10) + 'allow = ["abc"]' + chr(10),
    )  # fmt: skip
    talk = Talk()

    assert go(["refatorar", "--plano"], talk, environ) == 0
    assert "complexity: limite max_ccn de python = 40" in talk.text
    assert "detectores de dados pessoais desligados" in talk.text
    assert "limiar de entropia mais alto (4.0)" in talk.text
    assert "valores liberados pelo repositório" in talk.text


def test_the_doctor_warns_when_golangci_lint_is_missing_but_does_not_require_it(
    tmp_path: Path,
) -> None:
    only_go = tmp_path / "bin"
    only_go.mkdir()
    program = only_go / ("go.exe" if sys.platform == "win32" else "go")
    program.write_text("x", encoding="utf-8")
    program.chmod(0o755)

    found, lint = doctor_module._go_checks({"PATH": str(only_go)})  # noqa: SLF001

    assert found.ok
    assert not lint.ok
    assert not lint.required
    assert "não suportado" in lint.detail
    assert "golangci-lint.run" in lint.fix


def test_the_doctor_requires_node_for_a_typescript_project(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    program = bin_dir / ("node.exe" if sys.platform == "win32" else "node")
    program.write_text("x", encoding="utf-8")
    program.chmod(0o755)

    (found,) = doctor_module._node_checks({"PATH": str(bin_dir)})  # noqa: SLF001
    (missing,) = doctor_module._node_checks({"PATH": str(tmp_path)})  # noqa: SLF001

    assert found.ok
    assert not missing.ok
    assert missing.required
    assert "nodejs.org" in missing.fix


def test_the_doctor_requires_dotnet_for_a_csharp_project(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    program = bin_dir / ("dotnet.exe" if sys.platform == "win32" else "dotnet")
    program.write_text("x", encoding="utf-8")
    program.chmod(0o755)

    (found,) = doctor_module._dotnet_checks({"PATH": str(bin_dir)})  # noqa: SLF001
    (missing,) = doctor_module._dotnet_checks({"PATH": str(tmp_path)})  # noqa: SLF001

    assert found.ok
    assert not missing.ok
    assert missing.required
    assert "dotnet.microsoft.com" in missing.fix


def test_the_doctor_requires_java_and_maven_for_a_java_project(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    suffix = ".exe" if sys.platform == "win32" else ""
    program = bin_dir / f"java{suffix}"
    program.write_text("x", encoding="utf-8")
    program.chmod(0o755)

    java, maven = doctor_module._java_checks({"PATH": str(bin_dir)})  # noqa: SLF001

    assert java.ok
    assert not maven.ok
    assert maven.required
    assert "maven.apache.org" in maven.fix
