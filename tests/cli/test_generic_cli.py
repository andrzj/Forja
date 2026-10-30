"""A CLI the Forja does not know, described by a command template in a settings file."""

from pathlib import Path

import pytest

from forja.cli.args import parse
from forja.cli.prepare import Refused, _used_models, choose_cli, cli_templates
from forja.cli.session import executor_ref
from forja.cli.settings import (
    Execucao,
    ModeloCli,
    Perfil,
    load_execucao,
    load_perfil,
    save_execucao,
)
from forja.core.adapters.executor import (
    GENERIC_ENVIRONMENT,
    AgentRequest,
    CommandTemplate,
    RolePermissions,
    template_adapter,
)
from forja.core.artifacts.models import Producer
from forja.executors import adapter_for
from forja.orchestrator.config import ExecutorRef

MODEL = ModeloCli(comando=["{executable}", "--file", "{package}"], ambiente=["MY_KEY"])


class Console:
    interactive = False

    def say(self, text: str = "") -> None:
        pass


def test_a_profile_describes_a_cli_in_a_table(tmp_path: Path) -> None:
    (tmp_path / "config.toml").write_text(
        '[clis.meu-agente]\ncomando = ["{executable}", "--stdin"]\npacote_por_stdin = true\n',
        encoding="utf-8",
    )
    model = load_perfil(tmp_path).clis["meu-agente"]
    assert model.comando == ["{executable}", "--stdin"]
    assert model.pacote_por_stdin
    assert model.versao == ["--version"]


def test_the_execution_file_keeps_the_description_it_wrote(tmp_path: Path) -> None:
    path = tmp_path / "execucao.toml"
    save_execucao(path, Execucao(cli="meu-agente", clis={"meu-agente": MODEL}))
    assert load_execucao(path).clis == {"meu-agente": MODEL}


def test_a_template_needs_a_command() -> None:
    with pytest.raises(ValueError, match="comando"):
        ModeloCli(comando=[])


def test_the_execution_file_wins_over_the_profile() -> None:
    other = ModeloCli(comando=["{executable}", "{package}", "--x"])
    found = cli_templates(Perfil(clis={"a": MODEL, "b": MODEL}), Execucao(clis={"a": other}))
    assert found["a"].argv == ("{executable}", "{package}", "--x")
    assert found["b"].argv == ("{executable}", "--file", "{package}")


def test_a_name_the_forja_knows_is_refused() -> None:
    with pytest.raises(Refused, match="clis.codex"):
        cli_templates(Perfil(clis={"codex": MODEL}), None)


def test_the_generic_cli_is_found_where_the_file_says(tmp_path: Path) -> None:
    program = tmp_path / "meu-agente.exe"
    program.write_text("", encoding="utf-8")
    saved = Execucao(cli="meu-agente", executavel=str(program))
    templates = cli_templates(Perfil(clis={"meu-agente": MODEL}), None)
    name, choice, offer = choose_cli(
        parse([]),
        saved,
        Perfil(),
        {},
        Console(),
        templates=templates,  # type: ignore[arg-type]
    )
    assert (name, choice.path, offer) == ("meu-agente", program, False)


def test_an_unknown_name_is_refused_and_the_generic_ones_are_listed() -> None:
    saved = Execucao(cli="nenhuma")
    templates = cli_templates(Perfil(clis={"meu-agente": MODEL}), None)
    with pytest.raises(Refused, match="meu-agente"):
        choose_cli(parse([]), saved, Perfil(), {}, Console(), templates=templates)  # type: ignore[arg-type]


def test_only_the_cli_the_run_uses_is_written_to_the_execution_file() -> None:
    profile = Perfil(clis={"a": MODEL, "b": MODEL})
    assert set(_used_models(profile, None, "a", "a", "codex")) == {"a"}


def test_the_adapter_calls_the_cli_the_template_describes(tmp_path: Path) -> None:
    template = MODEL.template()
    adapter = adapter_for("meu-agente", template)
    package = tmp_path / "package.md"
    request = AgentRequest(Producer.IMPLEMENTER, package, tmp_path, RolePermissions(True))
    plan = adapter.plan_invocation(
        request,
        adapter.permission_setup(Producer.IMPLEMENTER, request.permissions),
        Path("/bin/meu"),
    )
    assert plan.argv == (str(Path("/bin/meu")), "--file", str(package))
    assert adapter.discovery.executable_names == ("meu-agente",)
    assert adapter.env_allow == GENERIC_ENVIRONMENT | {"MY_KEY"}
    assert adapter.enforces_permissions is False


def test_the_executables_of_the_template_are_what_discovery_looks_for() -> None:
    adapter = template_adapter("x", CommandTemplate(("{package}",), executables=("a", "b")))
    assert adapter.discovery.executable_names == ("a", "b")


def test_the_reference_remembers_the_template_for_a_resumed_run() -> None:
    ref = executor_ref("meu-agente", Path("/bin/meu"), "1.0", template=MODEL.template())
    assert ref.enforces_permissions is False
    again = ExecutorRef.model_validate(ref.model_dump(mode="json"))
    assert again.template == MODEL.template()


def test_a_known_cli_has_no_template() -> None:
    assert executor_ref("codex", Path("/bin/codex"), "1.0").template is None
