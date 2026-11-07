"""The checks of the doctor one by one: each condition both ways, each boundary on the value."""

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from forja.cli import doctor as doctor_module
from forja.cli.detect import LOW_DISK_GIB, Detection
from forja.cli.doctor import Check, doctor, render, run_checks
from forja.cli.prepare import Refused
from forja.cli.settings import ModeloCli, Perfil


class Quiet:
    interactive = False

    def __init__(self) -> None:
        self.said: list[str] = []

    def say(self, text: str = "") -> None:
        self.said.append(text)

    def ask(self, question: str, *, default: str = "") -> str:
        return default


def detection(**changes: object) -> Detection:
    facts: dict[str, object] = {
        "cwd": Path(),
        "repo": None,
        "has_commits": True,
        "branch": "main",
        "head": "abc",
        "changed": (),
        "python": False,
        "gitleaks": True,
        "git": True,
        "disk_free_gib": 50.0,
        "jscpd": True,
    }
    return Detection(**{**facts, **changes})  # type: ignore[arg-type]


@pytest.fixture
def agent(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """The agent check and the other CLIs stubbed; the names the agent check was asked for."""
    asked: list[str] = []

    async def agent_check(name: str, *args: object) -> Check:
        asked.append(name)
        return Check("agente", True, "ok")

    async def none(*args: object) -> list[Check]:
        return []

    monkeypatch.setattr(doctor_module, "_agent_check", agent_check)
    monkeypatch.setattr(doctor_module, "_other_clis", none)
    return asked


def checks_of(found: Detection, profile: Perfil | None = None, **options: str) -> dict[str, Check]:
    done = asyncio.run(
        run_checks(found, profile or Perfil(), {"PATH": ""}, Quiet(), Path(), **options)
    )
    return {check.name: check for check in done}


def test_pytest_in_the_repository_is_found_by_the_interpreter_that_imports_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(doctor_module, "repo_python", lambda _repo: (sys.executable,))

    check = asyncio.run(doctor_module._pytest_in(tmp_path))  # noqa: SLF001

    assert check.ok
    assert check.detail == f"{sys.executable} importa pytest"
    assert check.fix == ""


def test_pytest_missing_in_the_repository_is_reported_with_the_fix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(doctor_module, "repo_python", lambda _repo: (sys.executable, "-S"))

    check = asyncio.run(doctor_module._pytest_in(tmp_path))  # noqa: SLF001

    assert not check.ok
    assert check.detail == f"{sys.executable} não importa pytest"
    assert check.fix


@pytest.mark.parametrize(
    ("cli", "configured", "expected"),
    [("a", "b", "a"), ("", "b", "b"), ("", "", "claude-code")],
)
def test_the_agent_checked_is_the_option_then_the_profile_then_the_default(
    agent: list[str], cli: str, configured: str, expected: str
) -> None:
    checks_of(detection(), Perfil(cli=configured), cli=cli)

    assert agent == [expected]


def test_the_disk_passes_at_the_limit_and_fails_below_it(agent: list[str]) -> None:
    assert checks_of(detection(disk_free_gib=LOW_DISK_GIB))["disco"].ok
    assert not checks_of(detection(disk_free_gib=LOW_DISK_GIB - 0.1))["disco"].ok


def test_the_repository_is_clean_only_when_nothing_is_changed(
    agent: list[str], tmp_path: Path
) -> None:
    clean = checks_of(detection(repo=tmp_path))["repositório limpo"]
    dirty = checks_of(detection(repo=tmp_path, changed=("a", "b")))["repositório limpo"]

    assert clean.ok
    assert clean.detail == "sem alterações não salvas"
    assert not dirty.ok
    assert dirty.detail == "2 arquivo(s) alterado(s)"


def test_semgrep_is_checked_for_a_named_config_or_for_rules_in_the_repository(
    agent: list[str], tmp_path: Path
) -> None:
    assert "semgrep" in checks_of(detection(), semgrep_config="r.yml")
    assert "semgrep" not in checks_of(detection())
    assert "semgrep" not in checks_of(detection(repo=tmp_path))
    (tmp_path / ".semgrep.yml").write_text("x", encoding="utf-8")
    assert "semgrep" in checks_of(detection(repo=tmp_path))


def test_the_other_clis_listed_are_the_installed_ones_but_the_chosen(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def version(*args: object) -> str:
        return ""

    monkeypatch.setattr(doctor_module, "KNOWN_CLIS", {"a": object, "b": object})
    monkeypatch.setattr(
        doctor_module, "installed_clis", lambda *_a, **_k: [SimpleNamespace(path="p")]
    )
    monkeypatch.setattr(doctor_module, "executable_version", version)

    found = asyncio.run(doctor_module._other_clis("a", Perfil(), {}))  # noqa: SLF001

    assert [check.name for check in found] == ["CLI b"]
    assert found[0].detail == "p (?) instalada"
    assert found[0].ok
    assert not found[0].required


@pytest.mark.parametrize("known", [True, False])
def test_a_cli_is_unknown_only_without_a_name_and_without_a_template(
    monkeypatch: pytest.MonkeyPatch, known: bool
) -> None:
    monkeypatch.setattr(doctor_module, "installed_clis", lambda *_a, **_k: [])
    if known:
        name, profile = "claude-code", Perfil()
    else:
        name, profile = "meu", Perfil(clis={"meu": ModeloCli(comando=["{executable}"])})

    check = asyncio.run(
        doctor_module._agent_check(name, profile, {}, Quiet(), Path())  # noqa: SLF001
    )

    assert check.detail == "não encontrada no PATH"


def test_the_render_shows_a_fix_only_under_a_failed_check_that_has_one() -> None:
    lines = render(
        [Check("a", False, "d", "fix-a"), Check("b", False, "d"), Check("c", True, "d", "fix-c")]
    )

    assert [line for line in lines if "->" in line] == ["        -> fix-a"]


def test_the_render_counts_only_the_failed_required_checks() -> None:
    passing = render([Check("a", True, "d"), Check("b", False, "d", required=False)])
    failing = render([Check("a", False, "d"), Check("b", False, "d"), Check("c", True, "d")])

    assert passing[-1] == "Tudo pronto."
    assert failing[-1] == "2 item(ns) a resolver."


@pytest.mark.parametrize(
    ("checks", "code"),
    [
        ([Check("a", True, "d")], 0),
        ([Check("a", False, "d", required=False)], 0),
        ([Check("a", False, "d")], 1),
        ([Check("a", True, "d"), Check("b", False, "d")], 1),
    ],
)
def test_the_doctor_fails_only_when_a_required_check_failed(
    monkeypatch: pytest.MonkeyPatch, checks: list[Check], code: int
) -> None:
    async def fixed(*args: object, **kwargs: object) -> list[Check]:
        return checks

    monkeypatch.setattr(doctor_module, "run_checks", fixed)

    assert asyncio.run(doctor(detection(), Perfil(), {}, Quiet(), Path())) == code


def test_a_name_that_no_one_knows_is_reported_with_the_known_ones() -> None:
    check = asyncio.run(
        doctor_module._agent_check("nenhuma", Perfil(), {}, Quiet(), Path())  # noqa: SLF001
    )

    assert not check.ok
    assert check.detail == "CLI desconhecida"
    assert "claude-code" in check.fix


def test_the_checks_of_each_language_are_added_for_a_repository_that_has_it(
    agent: list[str], tmp_path: Path
) -> None:
    found = checks_of(detection(repo=tmp_path, go=True, typescript=True, csharp=True, java=True))

    assert {"go", "golangci-lint", "node", "dotnet", "java"} <= set(found)


@pytest.fixture
def installed(monkeypatch: pytest.MonkeyPatch) -> None:
    async def version(*args: object) -> str:
        return "1.2.3"

    monkeypatch.setattr(
        doctor_module, "installed_clis", lambda *_a, **_k: [SimpleNamespace(path="p")]
    )
    monkeypatch.setattr(doctor_module, "executable_version", version)
    monkeypatch.setattr(doctor_module, "version_problem", lambda *_a: None)


def agent_check() -> Check:
    return asyncio.run(
        doctor_module._agent_check("claude-code", Perfil(), {}, Quiet(), Path())  # noqa: SLF001
    )


def test_an_agent_that_answers_the_test_task_is_ok(
    installed: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def proven(*args: object) -> str:
        return "ok"

    monkeypatch.setattr(doctor_module, "prove", proven)

    check = agent_check()

    assert check.ok
    assert check.detail == "p (1.2.3) responde a uma tarefa de teste"


def test_an_agent_with_an_old_version_is_reported(
    installed: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(doctor_module, "version_problem", lambda *_a: "muito antiga")

    check = agent_check()

    assert not check.ok
    assert check.detail == "muito antiga"
    assert check.fix == "atualize a CLI"


def test_an_agent_that_refuses_the_test_task_is_reported(
    installed: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def refused(*args: object) -> str:
        raise Refused("recusou")

    monkeypatch.setattr(doctor_module, "prove", refused)

    check = agent_check()

    assert not check.ok
    assert check.detail == "recusou"
