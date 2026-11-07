"""``_detect`` where git answers in ways a real repository rarely does."""

import asyncio
import shutil
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest

from forja.cli import detect as detect_module
from forja.cli.detect import Detection, _detect  # noqa: PLC2701


@dataclass
class Answer:
    exit_code: int
    lines: list[str]


def run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, **answers: Answer) -> Detection:
    """``top``, ``head`` and ``branch`` are what git says; the rest is as in a fresh repository."""
    said = {
        "top": Answer(0, [str(tmp_path)]),
        "head": Answer(0, ["abc"]),
        "branch": Answer(0, ["main"]),
        **answers,
    }

    class FakeGit:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        async def run(self, *args: str) -> Answer:
            if "--show-toplevel" in args:
                return said["top"]
            return said["branch"] if "--abbrev-ref" in args else said["head"]

        async def lines(self, *args: str) -> list[str]:
            return []

    monkeypatch.setattr(detect_module, "Git", FakeGit)
    monkeypatch.setattr(detect_module, "locate_in_path", lambda *_args, **_kwargs: "found")
    return asyncio.run(_detect(tmp_path, {}, tmp_path))


def test_the_free_disk_is_counted_in_gibibytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(shutil, "disk_usage", lambda _path: SimpleNamespace(free=3 * 2**30))

    assert run(tmp_path, monkeypatch).disk_free_gib == 3.0


@pytest.mark.parametrize("answer", [Answer(0, []), Answer(1, ["/somewhere"])])
def test_a_failed_or_empty_toplevel_means_no_repository(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, answer: Answer
) -> None:
    detection = run(tmp_path, monkeypatch, top=answer)

    assert detection.repo is None
    assert detection.has_commits is False


@pytest.mark.parametrize(
    ("answer", "expected"),
    [(Answer(0, ["main"]), "main"), (Answer(1, ["main"]), ""), (Answer(0, []), "")],
)
def test_the_branch_is_named_only_when_git_answered_with_a_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, answer: Answer, expected: str
) -> None:
    assert run(tmp_path, monkeypatch, branch=answer).branch == expected


def test_without_git_there_is_no_repository_and_no_question_to_git(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(detect_module, "locate_in_path", lambda *_args, **_kwargs: None)

    detection = asyncio.run(_detect(tmp_path, {}, tmp_path))

    assert not detection.git
    assert detection.repo is None
    assert detection.has_commits is False
