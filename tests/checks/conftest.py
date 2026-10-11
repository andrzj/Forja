from pathlib import Path

import pytest

from tests.checks.support import Scene
from tests.core.idempotency.conftest import Repo, repo  # noqa: F401 - re-exported as a fixture


@pytest.fixture
def scene(request: pytest.FixtureRequest, repo: Repo, tmp_path: Path) -> Scene:  # noqa: F811
    """Fake tools, unless the test module is the one about the real ones."""
    real = request.module.__name__.endswith("real_measurer")
    return Scene(repo, tmp_path / "scene", real=real)
