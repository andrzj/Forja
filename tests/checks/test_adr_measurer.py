"""The measurer finds what calls for a decision record from the commits of the task."""

import asyncio
from pathlib import Path

from forja.core.gates import Approved, Rejected
from tests.checks.support import SAMPLE, Scene, sinks
from tests.checks.test_change_record_measurer import documenter_context
from tests.core.idempotency.conftest import Repo, repo  # noqa: F401 - re-exported as a fixture

ADR = "# 0001. Use requests\n\n## Alternatives\n\nurllib\n\n## Consequences\n\nOne more package.\n"


def commit(repo: Repo, message: str = "refactor: change") -> None:  # noqa: F811
    repo.sh("add", "-A")
    repo.sh("commit", "-m", message, "--trailer", "Task-Id: t1")


def judged(scene: Scene) -> object:
    scene.write("README.md", "# sample\n")  # the stage has work of its own to judge
    outcome = asyncio.run(scene.measurer.judge(documenter_context(scene), sinks))
    return next(run.result for run in outcome.runs if run.check_id == "adr")


def report(scene: Scene) -> str:
    return asyncio.run(scene.measurer.adr_report(documenter_context(scene)))


def test_a_task_that_adds_no_dependency_and_no_module_owes_nothing(
    repo: Repo,  # noqa: F811
    tmp_path: Path,
) -> None:
    scene = Scene(repo, tmp_path / "scene")
    scene.write("src/sample/mod.py", SAMPLE["src/sample/mod.py"] + "\nX = 1\n")
    commit(repo)

    assert report(scene) == ""
    assert isinstance(judged(scene), Approved)


def test_a_dependency_the_task_added_calls_for_a_record_that_the_documenter_then_writes(
    repo: Repo,  # noqa: F811
    tmp_path: Path,
) -> None:
    scene = Scene(repo, tmp_path / "scene")
    scene.write(
        "pyproject.toml",
        SAMPLE["pyproject.toml"].replace("[project]\n", '[project]\ndependencies = ["requests"]\n'),
    )
    commit(repo)

    assert "new external dependency `requests` (pyproject.toml)" in report(scene)
    assert "docs/adr/0001-<short-title>.md" in report(scene)
    assert isinstance(judged(scene), Rejected)

    scene.write("docs/adr/0001-use-requests.md", ADR)

    assert isinstance(judged(scene), Approved)


def test_a_directory_with_a_production_file_the_task_added_is_a_new_module(
    repo: Repo,  # noqa: F811
    tmp_path: Path,
) -> None:
    scene = Scene(repo, tmp_path / "scene")
    scene.write("src/sample/net/client.py", "def get() -> int:\n    return 1\n")
    commit(repo)

    assert "new module `src/sample/net` (src/sample/net/client.py)" in report(scene)
