import shutil
from pathlib import Path

import pytest

from forja.core.authorization import ProtectedBranches
from forja.core.gitguard import GuardedGit
from tests.core.idempotency.conftest import Repo, new_remote, repo  # noqa: F401


@pytest.fixture
def guard(repo: Repo, tmp_path: Path) -> GuardedGit:  # noqa: F811
    return GuardedGit(
        repo.path,
        executable=shutil.which("git") or "git",
        env={
            **repo.env,
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@example.com",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@example.com",
        },
        timeout=30,
        log_dir=tmp_path / "guard-logs",
        protected=ProtectedBranches(frozenset({"main"})),
    )
