"""The property-test instruction: the library of each language, and nothing for Java yet."""

import re

from forja.checks.voice_markers import MARKERS
from forja.orchestrator.properties_brief import brief

SUPPORTED = ("python", "typescript", "go", "csharp")


def test_each_supported_language_gets_its_own_library() -> None:
    for language, name, library in (
        ("python", "Python", "Hypothesis"),
        ("typescript", "TypeScript", "fast-check"),
        ("go", "Go", "pgregory.net/rapid"),
        ("csharp", "C#", "FsCheck"),
    ):
        text = brief([language])

        assert library in text, language
        assert text.count(f"- {name}: ") == 1, language


def test_a_language_not_in_the_repository_is_left_out() -> None:
    text = brief(["python"])

    assert "fast-check" not in text
    assert "rapid" not in text
    assert "FsCheck" not in text


def test_several_languages_get_every_library() -> None:
    text = brief(iter(SUPPORTED))

    assert all(library in text for library in ("Hypothesis", "fast-check", "rapid", "FsCheck"))


def test_java_and_unknown_languages_get_no_instruction() -> None:
    assert brief(["java"]) == ""
    assert brief(["java", "cobol"]) == ""
    assert brief([]) == ""


def test_java_is_left_out_of_a_mixed_repository() -> None:
    assert "jqwik" not in brief(["java", "python"])


def test_the_languages_without_a_forja_seed_are_told_to_fix_it_in_the_test() -> None:
    assert "`seed`" in brief(["typescript"])
    assert "`Replay`" in brief(["csharp"])
    assert "fixes the seed" in brief(["python"])
    assert "fixes the seed" in brief(["go"])


def test_the_brief_says_when_to_write_a_property() -> None:
    text = brief(["python"])

    assert "undoes each other" in text
    assert "dependency manifest" in text


def test_the_brief_obeys_the_voice_rules() -> None:
    text = brief(SUPPORTED)

    assert not re.search("[—–]| -- ", text)
    assert not any(marker.pattern.search(line) for line in text.splitlines() for marker in MARKERS)
