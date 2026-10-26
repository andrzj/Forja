"""Gate 13 judges whoever states something: the implementer and the test author too, when their
answer holds claims. With no claim there is nothing to cite and the gate does not run."""

import asyncio
from pathlib import Path

from forja.core.artifacts.llm_output import Claim, FileCitation
from forja.core.artifacts.models import Producer
from forja.core.gates import Approved, Rejected
from forja.orchestrator.ports import AttemptContext, Expectations, TaskInfo
from tests.checks.support import Scene, sinks
from tests.core.idempotency.conftest import Repo, repo  # noqa: F401 - re-exported as a fixture

NOWHERE = Claim(
    statement="the loop is gone",
    citations=(FileCitation(kind="file", path="src/none.py", line_start=1, line_end=1),),
)


def judge(scene: Scene, role: Producer, expectations: Expectations | None) -> dict[str, object]:
    scene.write("src/sample/mod.py", "def add(a: int, b: int) -> int:\n    return b + a\n")
    task = TaskInfo("t1", "t1-s", "intent", ("src/sample/mod.py",), 8, 400, role)
    context = AttemptContext(task, "t1-sa1", scene.repo.path, None)
    outcome = asyncio.run(scene.measurer.judge(context, sinks, expectations))
    return {run.check_id: run.result for run in outcome.runs}


def test_a_claim_that_cites_nothing_real_is_found_by_gate_13(
    repo: Repo,  # noqa: F811
    tmp_path: Path,
) -> None:
    scene = Scene(repo, tmp_path / "scene")

    results = judge(scene, Producer.IMPLEMENTER, Expectations(frozenset(), (), (NOWHERE,)))

    found = results["citations"]
    assert isinstance(found, Rejected)
    assert [f.target for f in found.findings] == ["src/none.py"]


def test_without_claims_the_gate_does_not_run_for_the_implementer(
    repo: Repo,  # noqa: F811
    tmp_path: Path,
) -> None:
    scene = Scene(repo, tmp_path / "scene")

    assert "citations" not in judge(scene, Producer.IMPLEMENTER, None)


def test_a_claim_that_cites_a_real_file_passes(
    repo: Repo,  # noqa: F811
    tmp_path: Path,
) -> None:
    scene = Scene(repo, tmp_path / "scene")
    real = Claim(
        statement="it is there",
        citations=(FileCitation(kind="file", path="src/sample/mod.py", line_start=1, line_end=1),),
    )

    results = judge(scene, Producer.IMPLEMENTER, Expectations(frozenset(), (), (real,)))

    assert isinstance(results["citations"], Approved)
