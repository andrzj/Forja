"""The module depth check: a new or shallower module that shows as much as it hides is reproved."""

import asyncio
from pathlib import Path

from forja.checks.changes import read_before, read_changes
from forja.checks.module_depth import DEFAULT_MAX_RATIO, DEFAULT_MIN_STATEMENTS, ModuleDepthCheck
from forja.core.gates import GateInput
from forja.core.gates.models import Approved, GateResult, Inconclusive, Rejected
from tests.checks.support import Scene

MOD = "src/sample/fresh.py"  # not in the sample project, so it has no past
OLD = "src/sample/mod.py"  # in the sample project, as one tiny function


def shallow(count: int, params: str = "a, b") -> str:
    """``count`` public functions, each with a one-line body."""
    return "".join(f"def f{i}({params}):\n    return a\n\n\n" for i in range(count))


def deep() -> str:
    """One public function with a long body: a small surface over a lot of work."""
    body = "".join(f"    x{i} = a + {i}\n" for i in range(20))
    return f"def run(a):\n{body}    return x0\n"


def judge(scene: Scene, path: str = MOD, **thresholds: float) -> GateResult:
    git = scene.repo.git.at(scene.repo.path)
    changes = asyncio.run(read_changes(git))
    before = asyncio.run(read_before(git, changes, (".py",)))
    check = ModuleDepthCheck(scene.repo.path, changes, (path,), before)
    values = {"thresholds": {"python": thresholds}} if thresholds else {}
    data = GateInput(Path("."), "c" * 40, "t", "s", "a", values=values)  # type: ignore[arg-type]
    return asyncio.run(check.evaluate(data))


def test_the_defaults_are_a_ratio_of_one_over_ten_statements() -> None:
    assert (DEFAULT_MAX_RATIO, DEFAULT_MIN_STATEMENTS) == (1.0, 10)


def test_a_new_shallow_module_is_rejected_with_its_ratio(scene: Scene) -> None:
    scene.write(MOD, shallow(8))  # surface 8 * 3 = 24 over 16 statements

    result = judge(scene)

    assert isinstance(result, Rejected)
    (finding,) = result.findings
    assert (finding.target, finding.measured, finding.limit) == (MOD, 1.5, 1.0)


def test_a_deep_module_is_approved(scene: Scene) -> None:
    scene.write(MOD, deep())

    assert isinstance(judge(scene), Approved)


def test_a_tiny_module_is_left_alone(scene: Scene) -> None:
    scene.write(MOD, shallow(2))  # ratio 1.5, but only 4 statements

    assert isinstance(judge(scene), Approved)


def test_the_policy_moves_the_limits(scene: Scene) -> None:
    scene.write(MOD, shallow(8))

    assert isinstance(judge(scene, max_interface_ratio=2), Approved)
    assert isinstance(judge(scene, min_statements=50), Approved)


def test_an_old_shallow_module_that_did_not_get_shallower_is_not_reproved(scene: Scene) -> None:
    scene.write(OLD, shallow(8))
    scene.repo.sh("add", "-A")
    scene.repo.sh("commit", "-m", "old debt")
    scene.write(OLD, shallow(8) + "X = 1\n")

    assert isinstance(judge(scene, OLD), Approved)


def test_a_module_that_got_shallower_is_reproved(scene: Scene) -> None:
    scene.write(OLD, shallow(8))
    scene.repo.sh("add", "-A")
    scene.repo.sh("commit", "-m", "old debt")
    scene.write(OLD, shallow(8, "a, b, c"))  # same code, a wider surface

    assert isinstance(judge(scene, OLD), Rejected)


def test_a_file_that_does_not_parse_is_inconclusive(scene: Scene) -> None:
    scene.write(MOD, "def broken(:\n")

    assert isinstance(judge(scene), Inconclusive)
