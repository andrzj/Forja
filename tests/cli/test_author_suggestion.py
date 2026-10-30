"""With one CLI chosen and others installed, the summary suggests another one for the tests."""

import pytest

from forja.cli import prepare as preparation
from forja.cli.prepare import suggest_author
from forja.cli.settings import Perfil


def installed(names: set[str]):
    def find(name: str, *args: object, **kwargs: object) -> list[object]:
        return [object()] if name in names else []

    return find


def test_it_names_the_other_installed_clis(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(preparation, "installed_clis", installed({"claude-code", "codex", "grok"}))
    line = suggest_author("claude-code", {}, Perfil())
    assert "codex, grok" in line
    assert "claude-code" not in line
    assert "--cli-testes" in line


def test_it_stays_quiet_when_no_other_is_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(preparation, "installed_clis", installed({"claude-code"}))
    assert suggest_author("claude-code", {}, Perfil()) == ""
