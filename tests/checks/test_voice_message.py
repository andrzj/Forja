"""The voice profile reads the commit message too; the repository's list changes the markers."""

import asyncio
from pathlib import Path

from forja.checks.changes import Changes
from forja.checks.voice import VoiceCheck
from forja.checks.voice_markers import MARKERS, build_markers
from forja.core.adapters import FileClass
from forja.core.gates import Approved, GateInput, GateResult, Rejected

DASH = chr(0x2014)


def judge(message: str, markers: tuple = MARKERS, tmp_path: Path = Path(".")) -> GateResult:  # type: ignore[type-arg]
    check = VoiceCheck(tmp_path, Changes((), 0, ()), lambda p: FileClass.OTHER, markers, message)
    return asyncio.run(check.evaluate(GateInput(tmp_path, "c" * 40, "t1", "t1-s", "t1-a1")))


def test_a_marker_in_the_commit_message_is_found_and_named_by_what_it_is() -> None:
    result = judge("Sure! The function is simpler now.")
    assert isinstance(result, Rejected)
    assert [(f.target, f.message) for f in result.findings] == [
        ("commit message", "commit message: an opening that greets instead of saying something")
    ]


def test_too_many_dashes_in_the_commit_message_are_excess() -> None:
    result = judge(f"a {DASH} b {DASH} c {DASH} d {DASH} e")
    assert isinstance(result, Rejected)
    assert result.findings[0].message == "too many em dashes in the commit message"
    assert (result.findings[0].measured, result.findings[0].limit) == (4, 3)


def test_dashes_at_the_limit_are_not_excess() -> None:
    assert isinstance(judge(f"a {DASH} b {DASH} c {DASH} d"), Approved)


def test_the_repositorys_own_patterns_are_numbered_from_one() -> None:
    own = build_markers(extra=["a", "b"])[-2:]
    assert [m.id for m in own] == ["repository-1", "repository-2"]


def test_a_plain_message_and_no_message_are_approved() -> None:
    assert isinstance(judge("Split the parser so each rule has one function."), Approved)
    assert isinstance(judge(""), Approved)


def test_the_repository_turns_markers_off_and_adds_its_own() -> None:
    kept = build_markers(off=["greeting"])
    assert "greeting" not in {m.id for m in kept}
    assert isinstance(judge("Sure! it is fine.", kept), Approved)

    own = build_markers(extra=[r"\bsynergy\b"])
    result = judge("Better synergy between modules.", own)
    assert isinstance(result, Rejected)
    assert result.findings[0].message == "commit message: a pattern the repository forbids"


def test_an_id_nobody_has_leaves_the_list_as_strict_as_it_was() -> None:
    assert [m.id for m in build_markers(off=["nonexistent"])] == [m.id for m in MARKERS]
