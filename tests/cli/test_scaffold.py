"""The scaffold of ``forja criar``: files from the template, a repository, one commit, the setup."""

import asyncio
import os
import subprocess
import sys
from pathlib import Path

import pytest

from forja.cli import scaffold as scaffolding
from forja.cli.scaffold import ScaffoldError, leftovers, scaffold
from forja.core.adapters import ProjectTemplate
from forja.orchestrator.config import CreateRequest

pytestmark = pytest.mark.integration

REQUEST = CreateRequest(description="an adder", language="python", name="my-adder")


def git(root: Path, *args: str) -> list[str]:
    done = subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True, check=True, encoding="utf-8"
    )
    return done.stdout.splitlines()


@pytest.fixture
def root(tmp_path: Path) -> Path:
    path = tmp_path / "new"
    path.mkdir()
    return path


def make(root: Path, request: CreateRequest = REQUEST) -> str:
    return asyncio.run(scaffold(root, request, dict(os.environ)))


def test_an_empty_directory_becomes_a_repository_with_the_template_in_one_commit(
    root: Path,
) -> None:
    head = make(root)

    assert git(root, "rev-parse", "HEAD") == [head]
    assert git(root, "rev-list", "--count", "HEAD") == ["1"]
    assert git(root, "log", "-1", "--format=%s") == ["chore: scaffold python project my-adder"]
    assert git(root, "rev-parse", "--abbrev-ref", "HEAD") == ["main"]
    assert git(root, "status", "--porcelain") == []
    tracked = git(root, "ls-files")
    assert "pyproject.toml" in tracked
    assert "src/my_adder/__init__.py" in tracked
    assert ".gitattributes" in tracked


def test_the_commit_is_the_forjas_and_the_committer_is_the_one_git_has(root: Path) -> None:
    make(root)

    assert git(root, "log", "-1", "--format=%an")[0].startswith("Forja (andaime")


def test_a_repository_with_no_commit_is_used_as_it_is(root: Path) -> None:
    git(root, "init", "-q", "-b", "trunk")

    head = make(root)

    assert git(root, "rev-parse", "HEAD") == [head]
    assert git(root, "rev-parse", "--abbrev-ref", "HEAD") == ["trunk"]


def test_the_hooks_of_a_repository_that_was_already_there_do_not_run(root: Path) -> None:
    git(root, "init", "-q")
    hook = root / ".git" / "hooks" / "pre-commit"
    hook.write_text("#!/bin/sh\ntouch ../hook-ran\nexit 1\n", encoding="utf-8", newline="\n")
    hook.chmod(0o755)

    make(root)

    assert git(root, "rev-list", "--count", "HEAD") == ["1"]
    assert not (root.parent / "hook-ran").exists()
    assert not (root / ".git" / "hook-ran").exists()


def test_a_directory_with_anything_in_it_is_refused_and_left_alone(root: Path) -> None:
    (root / "notes.txt").write_text("mine\n", encoding="utf-8")

    with pytest.raises(ScaffoldError, match="notes.txt"):
        make(root)

    assert leftovers(root) == ["notes.txt"]
    assert not (root / ".git").exists()


def test_leftovers_ignore_the_git_directory_only(root: Path) -> None:
    git(root, "init", "-q")
    assert leftovers(root) == []
    (root / ".gitignore").write_text("x\n", encoding="utf-8")
    assert leftovers(root) == [".gitignore"]


def with_setup(monkeypatch: pytest.MonkeyPatch, *commands: tuple[str, ...]) -> None:
    files = {"a.txt": "a\n"}
    monkeypatch.setattr(
        scaffolding, "project_template", lambda language, name: ProjectTemplate(files, commands)
    )
    monkeypatch.setattr(scaffolding, "locate_in_path", lambda name: Path(sys.executable))


def test_the_setup_runs_in_the_root_of_the_project(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with_setup(monkeypatch, ("python", "-c", "open('ran.txt', 'w').write('yes')"))

    make(root)

    assert (root / "ran.txt").read_text(encoding="utf-8") == "yes"


def test_a_setup_that_fails_says_so_and_that_the_project_is_already_committed(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with_setup(monkeypatch, ("python", "-c", "print('no network'); raise SystemExit(3)"))

    with pytest.raises(ScaffoldError) as raised:
        make(root)

    assert "falhou (3)" in raised.value.message
    assert "no network" in raised.value.message
    assert "criado e comitado" in raised.value.message
    assert git(root, "rev-list", "--count", "HEAD") == ["1"]


def test_a_setup_tool_that_is_not_installed_is_named(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with_setup(monkeypatch, ("npm", "install"))
    monkeypatch.setattr(scaffolding, "locate_in_path", lambda name: None)

    with pytest.raises(ScaffoldError, match="`npm` não está instalado"):
        make(root)


def test_a_setup_that_takes_too_long_is_stopped(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with_setup(monkeypatch, ("python", "-c", "import time; time.sleep(30)"))
    monkeypatch.setattr(scaffolding, "SETUP_SECONDS", 0.3)

    with pytest.raises(ScaffoldError, match="interrompido"):
        make(root)
