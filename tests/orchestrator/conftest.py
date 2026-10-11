from pathlib import Path

import pytest

from forja.orchestrator.workspace_git import GitWorkspace
from tests.core.idempotency.conftest import Repo, repo  # noqa: F401 - the fixture is used below
from tests.orchestrator.harness import IDENTITY, RUN, build_template, make_workspace  # noqa: F401


@pytest.fixture
def workspace(repo: Repo, tmp_path: Path) -> GitWorkspace:  # noqa: F811
    return make_workspace(repo, tmp_path)


@pytest.fixture(scope="session")
def template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("template") / "repo"
    build_template(path)
    return path
