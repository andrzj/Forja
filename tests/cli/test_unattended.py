"""A run from ``--config`` has nobody to ask: a question becomes a refusal naming the file."""

from types import SimpleNamespace

import pytest

from forja.cli import prepare as preparation
from forja.cli.args import parse
from forja.cli.console import Unattended, choose
from forja.cli.prepare import Refused, choose_cli, objective_of
from forja.cli.settings import Execucao, Perfil


class Silent:
    interactive = True

    def __init__(self) -> None:
        self.said: list[str] = []
        self.asked: list[str] = []

    def say(self, text: str = "") -> None:
        self.said.append(text)

    def ask(self, question: str, *, default: str = "") -> str:
        self.asked.append(question)
        return "2"


def test_it_never_asks_even_when_the_terminal_could_answer() -> None:
    inner = Silent()
    console = Unattended(inner)
    assert console.interactive is False
    assert console.ask("qual?", default="x") == "x"
    assert inner.asked == []


def test_what_it_says_still_reaches_the_person() -> None:
    inner = Silent()
    Unattended(inner).say("oi")
    assert inner.said == ["oi"]


def test_a_menu_takes_the_default_without_asking() -> None:
    inner = Silent()
    assert choose(Unattended(inner), "?", ["a", "b"], default=1) == 0
    assert inner.asked == []


def test_a_missing_objective_is_refused_and_names_the_file() -> None:
    with pytest.raises(Refused, match="objetivo.*execucao.toml"):
        objective_of(parse([]), None, Unattended(Silent()))


def test_the_objective_in_the_file_is_used() -> None:
    saved = Execucao(objetivo="corrigir")
    assert objective_of(parse([]), saved, Unattended(Silent())) == "corrigir"


@pytest.mark.parametrize("tests", [False, True])
def test_two_installations_are_refused_and_listed(
    monkeypatch: pytest.MonkeyPatch, tests: bool
) -> None:
    found = [
        SimpleNamespace(path=f"/bin/{n}", source=SimpleNamespace(value="PATH")) for n in ("a", "b")
    ]
    monkeypatch.setattr(preparation, "installed_clis", lambda *args, **kwargs: found)
    saved = Execucao(cli_testes="claude-code") if tests else None
    with pytest.raises(Refused) as refusal:
        choose_cli(parse([]), saved, Perfil(), {}, Unattended(Silent()), tests=tests)
    message = str(refusal.value)
    assert "2 instalações" in message
    assert ("executavel_testes" if tests else "executavel") in message
    assert "/bin/a" in message
    assert "/bin/b" in message
