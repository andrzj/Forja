"""The measurer judges the specifier by three checks only, and writes nothing about the code."""

import asyncio
from pathlib import Path

from forja.core.artifacts.elements import elements_of
from forja.core.artifacts.llm_output import (
    Claim,
    Criterion,
    CriterionLevel,
    FileCitation,
    LeftOut,
)
from forja.core.artifacts.models import Producer
from forja.core.gates import Approved, Rejected
from forja.orchestrator.ports import AttemptContext, Expectations, TaskInfo
from tests.checks.support import Scene, sinks
from tests.core.idempotency.conftest import Repo, repo  # noqa: F401 - re-exported as a fixture

ELEMENTS = elements_of("- add sums\n- add handles zero")


def specifier_context(scene: Scene) -> AttemptContext:
    task = TaskInfo("t1", "t1-c", "- add sums\n- add handles zero", (), 8, 400, Producer.SPECIFIER)
    return AttemptContext(task, "t1-ca1", scene.repo.path, None)


def criterion(number: int, *origin: str) -> Criterion:
    return Criterion(id=number, text="t", level=CriterionLevel.UNIT, origin=origin)


def judge(scene: Scene, expectations: Expectations) -> dict[str, object]:
    outcome = asyncio.run(scene.measurer.judge(specifier_context(scene), sinks, expectations))
    return {run.check_id: run.result for run in outcome.runs}


def test_only_scope_citations_and_traceability_run_for_the_specifier(
    repo: Repo,  # noqa: F811
    tmp_path: Path,
) -> None:
    scene = Scene(repo, tmp_path / "scene")
    expectations = Expectations(
        frozenset(), (), (), ELEMENTS, (criterion(1, "E1"), criterion(2, "E2"))
    )

    results = judge(scene, expectations)

    assert list(results) == ["scope", "citations", "traceability"]
    assert all(isinstance(result, Approved) for result in results.values())


def test_an_element_without_a_criterion_is_found_by_the_traceability_gate(
    repo: Repo,  # noqa: F811
    tmp_path: Path,
) -> None:
    scene = Scene(repo, tmp_path / "scene")

    results = judge(scene, Expectations(frozenset(), (), (), ELEMENTS, (criterion(1, "E1"),)))

    found = results["traceability"]
    assert isinstance(found, Rejected)
    assert [f.target for f in found.findings] == ["E2"]


def test_an_element_left_out_with_a_reason_passes(
    repo: Repo,  # noqa: F811
    tmp_path: Path,
) -> None:
    scene = Scene(repo, tmp_path / "scene")
    left = LeftOut(element="E2", reason="r", missing_evidence="m")

    results = judge(
        scene, Expectations(frozenset(), (), (), ELEMENTS, (criterion(1, "E1"),), (left,))
    )

    assert isinstance(results["traceability"], Approved)


def test_a_claim_of_the_specifier_that_cites_nothing_real_is_found_by_gate_13(
    repo: Repo,  # noqa: F811
    tmp_path: Path,
) -> None:
    scene = Scene(repo, tmp_path / "scene")
    nowhere = Claim(
        statement="add is slow",
        citations=(FileCitation(kind="file", path="src/none.py", line_start=1, line_end=1),),
    )
    expectations = Expectations(frozenset(), (), (nowhere,), ELEMENTS, (criterion(1, "E1", "E2"),))

    results = judge(scene, expectations)

    found = results["citations"]
    assert isinstance(found, Rejected)
    assert [f.target for f in found.findings] == ["src/none.py"]


def test_a_specifier_that_wrote_a_file_is_stopped_by_the_scope(
    repo: Repo,  # noqa: F811
    tmp_path: Path,
) -> None:
    scene = Scene(repo, tmp_path / "scene")
    scene.write("docs/criteria.md", "1. add sums\n")
    expectations = Expectations(
        frozenset(), (), (), ELEMENTS, (criterion(1, "E1"), criterion(2, "E2"))
    )

    results = judge(scene, expectations)

    assert isinstance(results["scope"], Rejected)
    assert list(results) == ["scope"]


def test_a_claim_that_cites_a_recorded_fact_passes_gate_13_and_an_unknown_one_does_not(
    repo: Repo,  # noqa: F811
    tmp_path: Path,
) -> None:
    from forja.core.artifacts.llm_output import FactCitation  # noqa: PLC0415

    scene = Scene(repo, tmp_path / "scene", gate_10={"fact_ids": frozenset({"F1"})})
    known = Claim(statement="pages hold 10", citations=(FactCitation(kind="fact", fact_id="F1"),))
    unknown = Claim(statement="pages hold 20", citations=(FactCitation(kind="fact", fact_id="F9"),))
    criteria = (criterion(1, "E1", "E2"),)

    good = judge(scene, Expectations(frozenset(), (), (known,), ELEMENTS, criteria))
    bad = judge(scene, Expectations(frozenset(), (), (unknown,), ELEMENTS, criteria))

    assert isinstance(good["citations"], Approved)
    assert isinstance(bad["citations"], Rejected)
    assert [f.target for f in bad["citations"].findings] == ["F9"]


def test_only_scope_and_citations_run_for_the_archaeologist(
    repo: Repo,  # noqa: F811
    tmp_path: Path,
) -> None:
    scene = Scene(repo, tmp_path / "scene")
    task = TaskInfo("t1", "t1-f", "how?", (), 8, 400, Producer.ARCHAEOLOGIST)
    nowhere = Claim(
        statement="add is slow",
        citations=(FileCitation(kind="file", path="src/none.py", line_start=1, line_end=1),),
    )

    outcome = asyncio.run(
        scene.measurer.judge(
            AttemptContext(task, "t1-fa1", scene.repo.path, None),
            sinks,
            Expectations(frozenset(), (), (nowhere,)),
        )
    )

    results = {run.check_id: run.result for run in outcome.runs}
    assert list(results) == ["scope", "citations"]
    assert isinstance(results["scope"], Approved)
    assert isinstance(results["citations"], Rejected)
