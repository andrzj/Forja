"""The documents the task changed, as the summary lists them."""

import asyncio
from pathlib import Path

from forja.checks.change_record import diary_path, record_path
from tests.checks.support import SAMPLE, Scene
from tests.core.idempotency.conftest import Repo, repo  # noqa: F401 - re-exported as a fixture

MOD = SAMPLE["src/sample/mod.py"]


def test_the_documents_are_the_ones_the_task_changed_besides_its_own_record_and_diary(
    repo: Repo,  # noqa: F811
    tmp_path: Path,
) -> None:
    scene = Scene(repo, tmp_path / "scene")
    scene.write(
        "src/sample/mod.py", MOD + "\n\ndef sub(a: int, b: int) -> int:\n    return a - b\n"
    )
    repo.sh("add", "-A")
    repo.sh("commit", "-m", "refactor: change mod", "--trailer", "Task-Id: t1")
    scene.write("README.md", "# sample\n")
    scene.write("docs/guide.md", "guide\n")
    scene.write(record_path("t1"), "record\n")
    scene.write(diary_path("t1"), "diary\n")
    repo.sh("add", "-A")
    repo.sh("commit", "-m", "docs: describe", "--trailer", "Task-Id: t1")

    found = asyncio.run(scene.measurer.documents(scene.context()))

    assert found == ["README.md", "docs/guide.md"]
