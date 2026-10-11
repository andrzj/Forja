from pathlib import Path

import pytest

from tests.checks.support import Scene
from tests.core.idempotency.conftest import Repo, repo  # noqa: F401 - re-exported as a fixture


@pytest.fixture
def scene(repo: Repo, tmp_path: Path) -> Scene:  # noqa: F811
    return Scene(repo, tmp_path / "scene")
