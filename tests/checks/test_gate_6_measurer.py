"""Gate 6 inside the real pipeline: the E2E commands the policy declares run for every attempt and
twice on the base, and the personal data an attempt adds to a test is found."""

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from forja.core.gates import CheckSettings, Mode, NotApplicable
from forja.core.gates.models import Rejected
from tests.checks.support import Scene, judge_with
from tests.core.idempotency.conftest import Repo, repo  # noqa: F401 - re-exported as a fixture

EVERY_CHECK = (
    "scope", "secrets", "format", "lint", "build", "tests", "mutation", "complexity", "crap",
    "pass_through", "module_depth", "sast", "dependency_audit", "new_dependency", "e2e",
    "test_data",
)  # fmt: skip
FAKE_E2E = Path(__file__).with_name("fake_e2e.py")


def scene_with(repo: Repo, tmp_path: Path, **gate: Any) -> Scene:  # noqa: F811
    observing = {name: CheckSettings(Mode.OBSERVATION) for name in EVERY_CHECK}
    return Scene(repo, tmp_path / "scene", settings=observing, gate_10=gate)


def declared(mode: str) -> dict[str, tuple[str, ...]]:
    return {"python": (sys.executable, str(FAKE_E2E), mode)}


def test_without_a_declared_command_the_e2e_does_not_run(
    repo: Repo,  # noqa: F811
    tmp_path: Path,
) -> None:
    scene = scene_with(repo, tmp_path)
    scene.write("src/sample/mod.py", "X = 1\n")

    assert judge_with(scene, "e2e") == NotApplicable(missing_capability="e2e_command")


def test_an_attempt_whose_e2e_knocks_on_the_network_is_rejected(
    repo: Repo,  # noqa: F811
    tmp_path: Path,
) -> None:
    scene = scene_with(repo, tmp_path, e2e_commands=declared("net"))
    scene.write("src/sample/mod.py", "X = 1\n")

    result = judge_with(scene, "e2e")

    assert isinstance(result, Rejected)
    assert result.findings[0].message == "tried to reach the network"
    assert result.findings[0].target == "blocked.test:80"


def test_personal_data_added_to_a_test_is_found(
    repo: Repo,  # noqa: F811
    tmp_path: Path,
) -> None:
    scene = scene_with(repo, tmp_path)
    scene.write("tests/test_person.py", "CPF = '529.982.247-25'\n")

    result = judge_with(scene, "test_data")

    assert isinstance(result, Rejected)
    assert [f.target for f in result.findings] == ["tests/test_person.py"]


def test_personal_data_in_production_code_is_not_this_gates_business(
    repo: Repo,  # noqa: F811
    tmp_path: Path,
) -> None:
    scene = scene_with(repo, tmp_path)
    scene.write("src/sample/mod.py", "CPF = '529.982.247-25'\n")

    assert not isinstance(judge_with(scene, "test_data"), Rejected)


def test_the_base_that_knocks_on_the_network_is_a_problem(
    repo: Repo,  # noqa: F811
    tmp_path: Path,
) -> None:
    scene = scene_with(repo, tmp_path, e2e_commands=declared("net"))

    measured = asyncio.run(scene.measurer.baseline(scene.repo.path, scene.recorder.sinks))

    assert not measured.ok
    assert "e2e: the base tried to reach blocked.test:80" in measured.problems


def test_the_base_remembers_nothing_of_the_e2e_when_none_is_declared(
    repo: Repo,  # noqa: F811
    tmp_path: Path,
) -> None:
    scene = scene_with(repo, tmp_path)

    asyncio.run(scene.measurer.baseline(scene.repo.path, scene.recorder.sinks))

    saved = json.loads((scene.work / "run" / "base.json").read_text(encoding="utf-8"))
    assert "e2e_passing" not in saved
