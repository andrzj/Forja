"""The PATH lookup never finds a program in the current directory (it may be a stranger's repo)."""

import os
import sys
from pathlib import Path

import pytest

from forja.core.adapters.executor import locate_in_path


def program(directory: Path, name: str = "tool") -> Path:
    directory.mkdir(exist_ok=True)
    path = directory / (name + (".exe" if sys.platform == "win32" else ""))
    path.write_text("x", encoding="utf-8")
    path.chmod(0o755)
    return path


def test_a_program_in_an_absolute_entry_is_found(tmp_path: Path) -> None:
    found = program(tmp_path / "bin")
    assert locate_in_path("tool", str(tmp_path / "bin")) == found


def test_the_current_directory_is_never_searched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    program(tmp_path / "repo")
    monkeypatch.chdir(tmp_path / "repo")
    assert locate_in_path("tool", os.pathsep.join(["", ".", str(tmp_path / "repo")])) is None


def test_relative_entries_are_ignored(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    program(tmp_path / "bin")
    monkeypatch.chdir(tmp_path)
    assert locate_in_path("tool", "bin") is None


def test_a_missing_program_is_none(tmp_path: Path) -> None:
    assert locate_in_path("nothing-here", str(tmp_path)) is None


def test_a_directory_with_the_name_of_the_program_is_not_the_program(tmp_path: Path) -> None:
    (tmp_path / "bin" / "tool").mkdir(parents=True)

    assert locate_in_path("tool", str(tmp_path / "bin")) is None


@pytest.mark.skipif(sys.platform == "win32", reason="the executable bit is a POSIX idea")
def test_a_file_that_is_not_executable_is_not_the_program(tmp_path: Path) -> None:
    path = program(tmp_path / "bin")
    path.chmod(0o644)

    assert locate_in_path("tool", str(tmp_path / "bin")) is None
