import asyncio
import shutil
from pathlib import Path
from typing import Any

from forja.core.authorization import ProtectedBranches, detect_protected_branches
from forja.core.gitguard import GuardedGit
from forja.core.idempotency.git import GitResult
from tests.core.idempotency.conftest import Repo


def test_branch_names_are_matched_with_or_without_the_refs_prefix() -> None:
    protected = ProtectedBranches(frozenset({"main"}))

    assert protected.is_protected("main")
    assert protected.is_protected("refs/heads/main")
    assert not protected.is_protected("feature/main")
    assert not protected.is_protected("Main")


def test_without_a_remote_main_and_master_are_protected_and_the_user_can_add_more(
    repo: Repo,
) -> None:
    detected = asyncio.run(detect_protected_branches(repo.git, extra=["release"]))

    assert detected.names == {"main", "master", "release"}


def test_the_default_branch_of_the_remote_is_protected_instead_of_the_fallback(
    repo: Repo, new_remote: object, tmp_path: Path
) -> None:
    bare = tmp_path / "origin.git"
    repo.sh("init", "--bare", "-b", "main", str(bare), cwd=tmp_path)
    repo.sh("remote", "add", "origin", str(bare))
    repo.sh("push", "origin", "main:trunk")
    repo.sh("remote", "set-head", "origin", "trunk")

    detected = asyncio.run(detect_protected_branches(repo.git, extra=["release"]))

    assert detected.names == {"trunk", "release"}


def test_detection_works_through_the_guarded_git(repo: Repo, tmp_path: Path) -> None:
    guarded = GuardedGit(
        repo.path,
        executable=shutil.which("git") or "git",
        env=repo.env,
        timeout=30,
        log_dir=tmp_path / "guard-logs",
        protected=ProtectedBranches(frozenset({"main"})),
    )

    assert asyncio.run(detect_protected_branches(guarded)).names == {"main", "master"}


class _SaysSo:
    """A git that answers ``symbolic-ref`` with whatever the test needs, real or not."""

    def __init__(self, exit_code: int, lines: list[str]) -> None:
        self._result = GitResult(exit_code, lines)

    async def run(self, *args: str) -> GitResult:
        return self._result


def detected_from(exit_code: int, lines: list[str]) -> frozenset[str]:
    git: Any = _SaysSo(exit_code, lines)
    return asyncio.run(detect_protected_branches(git)).names


def test_a_default_branch_with_slashes_in_its_name_is_kept_whole() -> None:
    assert detected_from(0, ["origin/release/1.0"]) == {"release/1.0"}


def test_an_answer_that_is_not_a_remote_branch_means_the_fallback() -> None:
    assert detected_from(0, ["origin"]) == {"main", "master"}
    assert detected_from(0, []) == {"main", "master"}


def test_a_failed_command_means_the_fallback_whatever_it_printed() -> None:
    assert detected_from(128, ["origin/develop"]) == {"main", "master"}
