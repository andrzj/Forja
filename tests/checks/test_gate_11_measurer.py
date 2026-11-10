"""Gate 11 inside the real pipeline: the cases of the policy are judged against the base."""

import asyncio
import sys
from pathlib import Path

from forja.core.gates import CheckSettings, Inconclusive, Mode, NotApplicable, Rejected
from forja.core.policy.differential import DifferentialCase
from forja.orchestrator.summary import read_facts
from tests.checks.support import Scene, judge_with
from tests.checks.test_gate_6_measurer import EVERY_CHECK
from tests.core.idempotency.conftest import Repo, repo  # noqa: F401 - re-exported as a fixture

SHOW = "import sys; sys.stdout.write(open('src/sample/mod.py').read())"
APPEND = "import sys; open(sys.argv[1], 'a').write('x')"
COUNTING = (
    "import pathlib, sys; p = pathlib.Path(sys.argv[1]); "
    "n = int(p.read_text()) + 1 if p.exists() else 1; p.write_text(str(n)); print('run', n)"
)


def scene_for(repo: Repo, tmp_path: Path, *cases: DifferentialCase, **values: object) -> Scene:  # noqa: F811
    observing = {name: CheckSettings(Mode.OBSERVATION) for name in EVERY_CHECK}
    return Scene(
        repo,
        tmp_path / "scene",
        settings=observing,
        values={"differential": values} if values else None,
        gate_10={"differential_cases": cases},
    )


def measure_base(scene: Scene) -> None:
    asyncio.run(scene.measurer.baseline(scene.repo.path, scene.recorder.sinks))


def show() -> DifferentialCase:
    return DifferentialCase("show", (sys.executable, "-c", SHOW))


def test_without_cases_the_differential_does_not_run(repo: Repo, tmp_path: Path) -> None:  # noqa: F811
    scene = scene_for(repo, tmp_path)
    scene.write("src/sample/mod.py", "X = 1\n")

    assert judge_with(scene, "differential") == NotApplicable(
        missing_capability="differential_cases"
    )


def test_an_attempt_that_keeps_the_output_of_the_base_is_approved(
    repo: Repo,  # noqa: F811
    tmp_path: Path,
) -> None:
    scene = scene_for(repo, tmp_path, show(), thresholds={"python": {"max_time_ratio": 100}})
    measure_base(scene)

    assert judge_with(scene, "differential").result == "approved"


def test_an_attempt_that_changes_the_output_of_the_base_is_rejected(
    repo: Repo,  # noqa: F811
    tmp_path: Path,
) -> None:
    loose = {"python": {"max_time_ratio": 100, "max_memory_ratio": 100}}
    scene = scene_for(repo, tmp_path, show(), thresholds=loose)
    measure_base(scene)
    scene.write("src/sample/mod.py", "X = 2\n")

    result = judge_with(scene, "differential")

    assert isinstance(result, Rejected)
    assert [f.target for f in result.findings] == ["show: stdout"]


def test_an_attempt_judged_without_a_base_is_inconclusive(
    repo: Repo,  # noqa: F811
    tmp_path: Path,
) -> None:
    scene = scene_for(repo, tmp_path, show())

    result = judge_with(scene, "differential")

    assert isinstance(result, Inconclusive)
    assert "case show" in result.detail


def test_the_thresholds_are_those_of_the_languages_of_the_project(
    repo: Repo,  # noqa: F811
    tmp_path: Path,
) -> None:
    counter = tmp_path / "counter"
    case = DifferentialCase("n", (sys.executable, "-c", APPEND, str(counter)))
    scene = scene_for(repo, tmp_path, case, thresholds={"python": {"runs": 1}})
    measure_base(scene)
    counter.write_text("", encoding="utf-8")

    judge_with(scene, "differential")

    assert counter.read_text(encoding="utf-8") == "x"  # the policy's one run, not the default three


def test_the_base_tells_the_log_which_cases_it_put_in_quarantine(
    repo: Repo,  # noqa: F811
    tmp_path: Path,
) -> None:
    case = DifferentialCase("count", (sys.executable, "-c", COUNTING, str(tmp_path / "count")))
    scene = scene_for(repo, tmp_path, case)

    measure_base(scene)

    note = read_facts(scene.log.path).differential
    assert note["quarantined"] == ["count"] and note["quarantined_count"] == 1


def test_a_base_read_back_tells_the_log_again(repo: Repo, tmp_path: Path) -> None:  # noqa: F811
    case = DifferentialCase("count", (sys.executable, "-c", COUNTING, str(tmp_path / "count")))
    scene = scene_for(repo, tmp_path, case)

    measure_base(scene)
    first = read_facts(scene.log.path).differential
    lines = scene.log.path.read_bytes().count(b'"kind":"differential"')
    measure_base(scene)

    assert read_facts(scene.log.path).differential == first
    assert scene.log.path.read_bytes().count(b'"kind":"differential"') == lines + 1


def test_without_cases_the_base_tells_the_log_nothing(repo: Repo, tmp_path: Path) -> None:  # noqa: F811
    scene = scene_for(repo, tmp_path)

    measure_base(scene)

    assert read_facts(scene.log.path).differential == {}
