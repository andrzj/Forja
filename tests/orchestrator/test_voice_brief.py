"""The voice instruction: the rules of the humanizer, shaped by what the repository turned off."""

import re

import pytest

from forja.checks.voice_markers import MARKERS, build_markers
from forja.orchestrator.voice_brief import _INTRO, _OUTRO, _RULES, VERSION, brief


def test_the_brief_keeps_the_facts_of_its_source_and_adds_none() -> None:
    text = brief()

    assert "Keep every fact and add none" in text
    assert "Write only the text" in text
    assert "Match the repository" in text


def test_the_brief_obeys_its_own_rules() -> None:
    text = brief()

    assert not re.search("[—–]| -- ", text)  # em dash, en dash, double hyphen
    # the rules quote what they forbid as examples; the prose around them is the Forja's own
    prose = [*_INTRO.splitlines(), _OUTRO]
    assert not any(marker.pattern.search(line) for line in prose for marker in MARKERS)


def test_every_marker_id_a_rule_names_is_a_marker_of_the_list() -> None:
    ids = {marker.id for marker in MARKERS}

    assert {marker for marker, _ in _RULES if marker} <= ids


@pytest.mark.parametrize("marker", sorted({m for m, _ in _RULES if m}))
def test_a_marker_the_repository_turned_off_is_not_asked_for(marker: str) -> None:
    rule = next(rule for found, rule in _RULES if found == marker)

    assert f"- {rule}" in brief()
    assert f"- {rule}" not in brief(markers_off=(marker,))


def test_turning_off_a_marker_leaves_the_other_rules() -> None:
    kept = [rule for marker, rule in _RULES if marker != "offer"]

    text = brief(markers_off=("offer",))

    assert all(f"- {rule}" in text for rule in kept)


def test_a_marker_id_nobody_has_changes_nothing() -> None:
    assert brief(markers_off=("no-such-marker",)) == brief()


def test_the_patterns_the_repository_added_are_listed() -> None:
    text = brief(patterns=(r"\bsynergy\b", r"leverage"))

    assert "forbids text that matches these regular expressions" in text
    assert "- \\bsynergy\\b" in text and "- leverage" in text
    assert "forbids text that matches" not in brief()


def test_the_brief_ends_with_the_check_against_the_list_and_a_newline() -> None:
    text = brief()

    assert text.rstrip().endswith("fix what it catches.")
    assert text.endswith("\n") and not text.endswith("\n\n")


def test_the_brief_is_the_same_each_time() -> None:
    assert brief(("offer",), (r"x",)) == brief(("offer",), (r"x",))


def test_the_list_a_repository_edits_and_the_brief_agree_on_the_default_markers() -> None:
    kept = {marker.id for marker in build_markers(off=("offer",))}

    assert "offer" not in kept
    assert VERSION == 2


def test_emoji_is_part_of_the_voice_not_a_marker_nor_a_thing_to_avoid() -> None:
    text = brief()

    assert "emoji" not in {marker.id for marker in MARKERS}
    assert not any(rule == "Emoji." for _, rule in _RULES)
    assert "Emoji are part of the voice" in text
    assert not any(marker.pattern.search("Done 🚀") for marker in MARKERS)
