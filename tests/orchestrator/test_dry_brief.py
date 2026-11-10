"""The duplication instruction: the same limits the check applies, said to the agent."""

import re

from forja.checks.voice_markers import MARKERS
from forja.orchestrator.dry_brief import VERSION, brief


def test_the_brief_names_the_limits_it_is_given() -> None:
    text = brief(min_tokens=70, min_lines=9)

    assert "9 lines or 70 tokens" in text


def test_the_brief_leaves_old_duplication_alone_and_asks_for_one_place() -> None:
    text = brief(50, 5)

    assert "already there is not yours to fix" in text
    assert "one function or module" in text


def test_the_brief_says_what_to_do_when_an_owner_fact_asks_for_a_copy() -> None:
    text = brief(50, 5)

    assert "A fact from the owner may ask for a copy" in text
    assert "do not hide the clone by changing its structure" in text
    assert "leave it as it is and declare in `assumptions`" in text
    assert "with the id of the fact" in text


def test_the_brief_is_version_2() -> None:
    assert VERSION == 2


def test_the_brief_obeys_the_voice_rules() -> None:
    text = brief(50, 5)

    assert not re.search("[—–]| -- ", text)
    assert not any(marker.pattern.search(line) for line in text.splitlines() for marker in MARKERS)
