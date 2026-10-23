"""The measurer builds the record of a task from its commits, not from the documenter's work."""

import asyncio

from forja.core.artifacts.llm_output import Claim, FileCitation
from forja.core.artifacts.models import Executor
from forja.orchestrator.ports import RecordFile
from tests.checks.support import SAMPLE, Scene, sinks
from tests.core.idempotency.conftest import Repo, repo  # noqa: F401 - re-exported as a fixture

MOD = SAMPLE["src/sample/mod.py"]
CLAIM = Claim(
    statement="add is now the only function of the module",
    citations=(FileCitation(kind="file", path="src/sample/mod.py", line_start=1, line_end=2),),
)


def record_of(scene: Scene, gates: list[str]) -> RecordFile:
    executors = [Executor(cli="claude", version="2.0")]
    return asyncio.run(
        scene.measurer.change_record(scene.context(), sinks, [CLAIM], gates, executors)
    )


def commit_the_code(scene: Scene, repo: Repo, text: str) -> None:  # noqa: F811
    scene.write("src/sample/mod.py", text)
    repo.sh("add", "-A")
    repo.sh("commit", "-m", "refactor: change mod", "--trailer", "Task-Id: t1")


def test_the_record_lists_the_code_of_the_task_against_where_the_task_branch_started(
    repo: Repo,  # noqa: F811
    tmp_path: object,
) -> None:
    scene = Scene(repo, tmp_path / "scene")  # type: ignore[operator]
    commit_the_code(scene, repo, MOD + "\n\ndef sub(a: int, b: int) -> int:\n    return a - b\n")

    record = record_of(scene, ["build", "tests"])

    assert record.path == "docs/mudancas/t1.md"
    assert "- `src/sample/mod.py`: modified" in record.text
    assert "`sub` (function) em `src/sample/mod.py`: created" in record.text
    assert "- build\n- tests" in record.text
    assert "- CLI claude 2.0" in record.text
    assert f"git revert {repo.sh('rev-parse', 'HEAD').strip()}" in record.text
    assert "- add is now the only function of the module (`src/sample/mod.py:1-2`)" in record.text


def test_the_documenters_own_files_are_not_part_of_the_record(
    repo: Repo,  # noqa: F811
    tmp_path: object,
) -> None:
    scene = Scene(repo, tmp_path / "scene")  # type: ignore[operator]
    commit_the_code(scene, repo, MOD + "\n\ndef sub(a: int, b: int) -> int:\n    return a - b\n")
    scene.write("README.md", "# sample\n")
    scene.write("docs/guide.md", "guide\n")

    text = record_of(scene, []).text

    assert "README.md" not in text
    assert "docs/guide.md" not in text


def test_a_removed_symbol_is_proved_unused_by_the_files_that_remain(
    repo: Repo,  # noqa: F811
    tmp_path: object,
) -> None:
    scene = Scene(repo, tmp_path / "scene")  # type: ignore[operator]
    commit_the_code(scene, repo, "")

    text = record_of(scene, []).text

    assert "`add` (function) em `src/sample/mod.py`: removed; **símbolo público removido.**" in text
    assert "ainda mencionado em `tests/test_mod.py`" in text
