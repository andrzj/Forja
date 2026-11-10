"""The person who confirms a run is told what the repository changed in the voice list."""

from forja.checks.specs import default_registry
from forja.cli.prepare import policy_changes
from forja.core.policy.config import build_policy, parse_layer


def changes(toml: str) -> tuple[str, ...]:
    return policy_changes(build_policy(default_registry(), [parse_layer("repo", toml)]))


def test_markers_turned_off_and_patterns_added_are_listed_with_their_values() -> None:
    told = changes('[voice]\nmarkers_off = ["emoji"]\nmarkers_extra = ["syn"]\n')
    assert "voz: marcadores desligados pelo repositório: emoji" in told
    assert "voz: padrões proibidos pelo repositório: syn" in told


def test_a_repository_that_leaves_the_voice_list_alone_says_nothing_about_it() -> None:
    assert not [note for note in changes("") if note.startswith("voz")]


TOML_ADDITIONS = """
[sensitive]
paths = ["config/prod/**"]
[branches]
protected = ["release"]
[licenses]
forbidden = ["GPL-3.0-only"]
[tests]
root = "spec"
[redaction.patterns]
chave-interna = "intk_[a-z]{8}"
[[architecture.layers]]
name = "ui"
paths = ["src/ui"]
[[architecture.layers]]
name = "core"
paths = ["src/core"]
[[differential.cases]]
name = "relatorio"
command = ["python", "-m", "r"]
"""


def test_what_the_repository_adds_is_listed_with_its_values() -> None:
    told = changes(TOML_ADDITIONS)
    assert "arquivos sensíveis acrescentados: config/prod/**" in told
    assert "branches protegidas acrescentadas: release" in told
    assert any(note.lower() == "licenças proibidas: gpl-3.0-only" for note in told)
    assert "testes escritos em: spec" in told
    assert "redação: padrões acrescentados pelo repositório: chave-interna" in told
    assert "camadas de arquitetura (da mais alta para a mais baixa): ui > core" in told
    assert "casos do teste diferencial: relatorio" in told


def test_a_repository_without_additions_says_nothing_about_them() -> None:
    assert not changes("")
