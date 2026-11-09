"""The command line is short, and the files it reads say clearly what is wrong with them."""

from pathlib import Path

import pytest

from forja.cli.args import VERBS, parse, parser
from forja.cli.settings import (
    Execucao,
    Perfil,
    SettingsError,
    dumps,
    load_execucao,
    load_perfil,
    profile_dir,
    save_execucao,
    save_perfil,
)


def test_no_arguments_means_the_guided_way() -> None:
    args = parse([])
    assert (args.command, args.scope, args.cli, args.plan_only, args.config) == (
        "",
        (),
        "",
        False,
        None,
    )


def test_a_verb_takes_the_four_options_after_it_too() -> None:
    args = parse(
        ["refatorar", "--escopo", "src", "--escopo", "lib", "--cli", "claude-code", "--plano"]
    )
    assert (args.command, args.scope, args.cli, args.plan_only) == (
        "refatorar",
        ("src", "lib"),
        "claude-code",
        True,
    )


def test_options_before_the_verb_work_the_same() -> None:
    assert parse(["--escopo", "src", "refatorar"]).scope == ("src",)


def test_the_agent_commands_exist_but_are_not_in_the_help() -> None:
    assert parse(["agente", "testar", "a", "b"]).agent == ("testar", "a", "b")
    assert "agente," not in parser().format_help()
    assert "agente}" not in parser().format_help()
    assert "  agente " not in parser().format_help()


def test_every_verb_is_in_the_help() -> None:
    assert all(verb in parser().format_help() for verb in VERBS)


def test_an_unknown_command_is_refused() -> None:
    with pytest.raises(SystemExit):
        parse(["consertar"])


def test_execucao_survives_a_round_trip_with_awkward_text(tmp_path: Path) -> None:
    original = Execucao(
        cli="claude-code",
        executavel='C:\\Program Files\\claude "x"\\claude.exe',
        escopo=["src/a b", "lib"],
        tokens=123_456,
    )
    save_execucao(tmp_path / "execucao.toml", original)
    assert load_execucao(tmp_path / "execucao.toml") == original


def test_no_verb_description_carries_a_development_stage() -> None:
    assert not any("incremento" in text for text in VERBS.values())


def test_the_test_author_options_say_they_serve_fixing_and_creating() -> None:
    help_text = " ".join(parser().format_help().split())
    assert "escreve os testes (corrigir e criar)" in help_text


def test_a_key_that_nothing_reads_is_not_accepted(tmp_path: Path) -> None:
    (tmp_path / "e.toml").write_text('base = "main"\n', encoding="utf-8")
    with pytest.raises(SettingsError, match="base"):
        load_execucao(tmp_path / "e.toml")


def test_a_misspelled_key_is_named_not_ignored(tmp_path: Path) -> None:
    (tmp_path / "e.toml").write_text("tokenz = 5\n", encoding="utf-8")
    with pytest.raises(SettingsError, match="tokenz"):
        load_execucao(tmp_path / "e.toml")


def test_invalid_toml_and_a_missing_file_are_explained(tmp_path: Path) -> None:
    (tmp_path / "e.toml").write_text("tokens = = 1", encoding="utf-8")
    with pytest.raises(SettingsError, match="not valid TOML"):
        load_execucao(tmp_path / "e.toml")
    with pytest.raises(SettingsError, match="cannot read"):
        load_execucao(tmp_path / "missing.toml")


def test_tokens_must_be_positive(tmp_path: Path) -> None:
    (tmp_path / "e.toml").write_text("tokens = 0\n", encoding="utf-8")
    with pytest.raises(SettingsError, match="tokens"):
        load_execucao(tmp_path / "e.toml")


def test_the_profile_is_empty_until_saved_and_then_kept(tmp_path: Path) -> None:
    assert load_perfil(tmp_path) == Perfil()
    save_perfil(tmp_path / "novo", Perfil(cli="claude-code", executaveis={"claude-code": "/x/y"}))
    assert load_perfil(tmp_path / "novo").executaveis == {"claude-code": "/x/y"}


def test_the_profile_lives_where_each_system_keeps_settings(tmp_path: Path) -> None:
    assert profile_dir({"FORJA_CONFIG_HOME": str(tmp_path)}, "linux") == tmp_path
    assert profile_dir({"APPDATA": "C:/Roam"}, "win32") == Path("C:/Roam") / "forja"
    assert profile_dir({"XDG_CONFIG_HOME": "/cfg"}, "linux") == Path("/cfg") / "forja"
    assert profile_dir({}, "linux") == Path.home() / ".config" / "forja"


def test_dumps_writes_flat_values_before_tables() -> None:
    text = dumps({"a": 1, "t": {"b": True}, "c": ["x"]})
    assert text.index("a = 1") < text.index("c = ") < text.index("[t]") < text.index("b = true")
