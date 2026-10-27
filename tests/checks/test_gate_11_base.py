"""Gate 11 inside the pipeline: the base measures the declared cases once per execution."""

import asyncio
import sys
from pathlib import Path

from forja.checks.differential_base import INDEX, load
from forja.core.policy.differential import STDOUT, DifferentialCase
from forja.orchestrator.ports import Baseline
from tests.checks.support import Scene
from tests.checks.test_gate_6_measurer import scene_with
from tests.core.idempotency.conftest import Repo, repo  # noqa: F401 - re-exported as a fixture

COUNTING = (
    "import pathlib, sys; p = pathlib.Path(sys.argv[1]); "
    "n = int(p.read_text()) + 1 if p.exists() else 1; p.write_text(str(n)); print('hi')"
)


def baseline(scene: Scene) -> Baseline:
    return asyncio.run(scene.measurer.baseline(scene.repo.path, scene.recorder.sinks))


def test_without_cases_the_base_keeps_nothing(repo: Repo, tmp_path: Path) -> None:  # noqa: F811
    scene = scene_with(repo, tmp_path)

    baseline(scene)

    assert not scene.measurer.differential_directory.exists()


def test_the_base_measures_each_case_and_keeps_the_result(
    repo: Repo,  # noqa: F811
    tmp_path: Path,
) -> None:
    case = DifferentialCase("hello", (sys.executable, "-c", "print('hi')"))
    scene = scene_with(repo, tmp_path, differential_cases=(case,))

    measured = baseline(scene)

    assert measured.ok
    kept = load(scene.measurer.differential_directory, [case])
    assert kept is not None
    assert kept.cases["hello"].outputs[(STDOUT, "")] == b"hi\n"


def test_a_base_already_measured_is_read_back_not_run_again(
    repo: Repo,  # noqa: F811
    tmp_path: Path,
) -> None:
    counter = tmp_path / "counter"
    case = DifferentialCase("count", (sys.executable, "-c", COUNTING, str(counter)))
    scene = scene_with(repo, tmp_path, differential_cases=(case,))

    baseline(scene)
    baseline(scene)

    assert counter.read_text() == "2"  # two runs on the first call, none on the second
    assert (scene.measurer.differential_directory / INDEX).is_file()


def test_an_input_the_base_does_not_have_is_a_problem(
    repo: Repo,  # noqa: F811
    tmp_path: Path,
) -> None:
    case = DifferentialCase("in", (sys.executable, "-c", "pass"), stdin="absent.txt")
    scene = scene_with(repo, tmp_path, differential_cases=(case,))

    measured = baseline(scene)

    assert not measured.ok
    assert any(p.startswith("differential: ") for p in measured.problems)
