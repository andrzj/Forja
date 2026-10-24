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
