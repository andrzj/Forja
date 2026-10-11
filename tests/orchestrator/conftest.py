import shutil
from pathlib import Path

import pytest

from forja.core.authorization import ProtectedBranches
from forja.core.gitguard import GuardedGit
from forja.orchestrator.workspace_git import GitWorkspace, Identity, Layout, git_environment
from tests.core.idempotency.conftest import Repo, repo  # noqa: F401 - the fixture is used below

RUN = "r1abcdef0123"
IDENTITY = Identity("Forja (fake-cli)", "forja@localhost", "Dev Person", "dev@example.com")


@pytest.fixture
def workspace(repo: Repo, tmp_path: Path) -> GitWorkspace:  # noqa: F811
    git = GuardedGit(
        repo.path,
        executable=shutil.which("git") or "git",
        env=git_environment(repo.env, IDENTITY),
        timeout=60,
        log_dir=tmp_path / "logs" / "guard",
        protected=ProtectedBranches(frozenset({"main"})),
    )
    return GitWorkspace(git, run_id=RUN, layout=Layout(tmp_path / "wt"))
