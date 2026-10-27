"""Gate 9 inside the real pipeline: the three architecture checks are judged for every attempt,
over the project's graph in the parent commit and in the attempt."""

from pathlib import Path

from forja.core.gates import CheckSettings, Mode, NotApplicable
from forja.core.gates.models import Approved, Rejected
from forja.core.policy import ArchitectureLayer
from tests.checks.support import Scene, judge_with
from tests.core.idempotency.conftest import Repo, repo  # noqa: F401 - re-exported as a fixture

GATES = (
    "scope", "secrets", "format", "lint", "build", "tests", "mutation", "complexity", "crap",
    "pass_through", "module_depth", "dependency_cycles", "layer_rules", "package_metrics",
    "sast", "dependency_audit", "new_dependency", "e2e", "test_data", "voice", "comments",
)  # fmt: skip


def scene_with(repo: Repo, tmp_path: Path, **options: object) -> Scene:  # noqa: F811
    observing = {name: CheckSettings(Mode.OBSERVATION) for name in GATES}
    return Scene(repo, tmp_path / "scene", settings=observing, gate_10=options)


def write_cycle(scene: Scene) -> None:
    scene.write("a/__init__.py", "")
    scene.write("a/x.py", "from b import y\n")
    scene.write("b/__init__.py", "")
    scene.write("b/y.py", "from a import x\n")


def test_an_attempt_that_closes_a_cycle_between_directories_is_rejected(
    repo: Repo,  # noqa: F811
    tmp_path: Path,
) -> None:
    scene = scene_with(repo, tmp_path)
    write_cycle(scene)

    result = judge_with(scene, "dependency_cycles")

    assert isinstance(result, Rejected)
    assert result.findings[0].measured == 2


def test_an_attempt_that_adds_no_import_is_approved_by_the_three_checks(
    repo: Repo,  # noqa: F811
    tmp_path: Path,
) -> None:
    scene = scene_with(repo, tmp_path)
    scene.write("src/sample/mod.py", "def add(a: int, b: int) -> int:\n    return a + b + 0\n")

    assert judge_with(scene, "dependency_cycles") == Approved()
    assert judge_with(scene, "package_metrics") == Approved()


def test_an_edge_to_a_layer_above_is_rejected_with_the_layers_of_the_policy(
    repo: Repo,  # noqa: F811
    tmp_path: Path,
) -> None:
    layers = (ArchitectureLayer("top", ("a",)), ArchitectureLayer("bottom", ("b",)))
    scene = scene_with(repo, tmp_path, layers=layers)
    scene.write("a/__init__.py", "")
    scene.write("a/x.py", "VALUE = 1\n")
    scene.write("b/__init__.py", "")
    scene.write("b/y.py", "from a import x\n")

    result = judge_with(scene, "layer_rules")

    assert isinstance(result, Rejected)
    assert result.findings[0].target == "b -> a"


def test_without_layers_the_layer_check_does_not_run_and_says_so(
    repo: Repo,  # noqa: F811
    tmp_path: Path,
) -> None:
    scene = scene_with(repo, tmp_path)
    write_cycle(scene)

    assert judge_with(scene, "layer_rules") == NotApplicable(
        missing_capability="architecture_layers"
    )
