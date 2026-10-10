"""Fixtures shared by the end-to-end resume tests."""

import asyncio
from pathlib import Path
from typing import Any

import pytest

from tests.e2e.driver import drive
from tests.e2e.support import Counting, label
from tests.e2e.world import World, build_template, fingerprint, make_world


@pytest.fixture(scope="session")
def template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("template") / "repo"
    build_template(path)
    return path


@pytest.fixture
def world(tmp_path: Path, template: Path) -> World:
    return make_world(tmp_path / "world", template)


@pytest.fixture(scope="session")
def reference(tmp_path_factory: pytest.TempPathFactory, template: Path) -> dict[str, Any]:
    """The facts of a run nobody interrupted, plus the line number each event landed on."""
    world = make_world(tmp_path_factory.mktemp("reference") / "world", template)
    counter = Counting()
    marks: list[tuple[int, str, str]] = []
    with world.open_log(write=counter) as log:
        log.subscribe(lambda e: marks.append((counter.count, e.type, label(e))))
        asyncio.run(drive(world, log))
    return {"fingerprint": fingerprint(world), "lines": counter.count, "marks": marks}
