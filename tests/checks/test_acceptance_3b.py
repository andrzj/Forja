"""Acceptance of 3b: the two cases the plan names, judged by the real pipeline, checks blocking."""

from pathlib import Path

import pytest

from forja.core.gates.models import Approved, Rejected
from forja.core.gates.pipeline import Verdict
from tests.checks.support import BLOCKING, OBSERVATION, PREMISE, Scene, sinks
from tests.core.idempotency.conftest import Repo

pytest.importorskip("coverage")
pytestmark = pytest.mark.slow

MOD = "src/sample/mod.py"
TEST = "tests/test_mod.py"


def blocking(scene: Scene, *checks: str) -> Scene:
    standard = {
        name: BLOCKING for name in ("scope", "secrets", "format", "lint", "build", "tests")
    } | {"complexity": PREMISE}
    standard |= {
        c: OBSERVATION
        for c in (
            "mutation",
            "crap",
            "pass_through",
            "module_depth",
            "duplication",
            "types",
            "dependency_cycles",
            "layer_rules",
            "package_metrics",
            "sast",
            "dependency_audit",
            "new_dependency",
            "differential",
            "e2e",
            "test_data",
            "voice",
            "comments",
        )
    }
    scene.measurer = scene.make_measurer(settings=standard | {c: BLOCKING for c in checks})
    return scene


def run(scene: Scene) -> object:
    import asyncio  # noqa: PLC0415

    return asyncio.run(scene.measurer.judge(scene.context(), sinks))


def result_of(outcome: object, check: str) -> object:
    return next(r.result for r in outcome.runs if r.check_id == check)  # type: ignore[attr-defined]


def branches(first: int, last: int) -> str:
    return "".join(f"    if n == {i}:\n        return {i}\n" for i in range(first, last))


BIG = f"def big(n: int) -> int:\n{branches(0, 12)}    return -1\n"
CHECKS = (
    "from sample.mod import big\n\n\ndef test_big() -> None:\n"
    + "".join(f"    assert big({i}) == {i}\n" for i in range(12))
    + "    assert big(99) == -1\n"
)
SPLIT = (
    f"def _low(n: int) -> int:\n{branches(0, 6)}    return -1\n\n\n"
    f"def _high(n: int) -> int:\n{branches(6, 12)}    return -1\n\n\n"
    "def _pick(n: int) -> int:\n    first = _low(n)\n"
    "    return first if first != -1 else _high(n)\n\n\n"
    "def big(n: int) -> int:\n    return _pick(n)\n"
)


def test_a_split_that_lowers_crap_but_leaves_a_forwarder_is_rejected(
    repo: Repo, tmp_path: Path
) -> None:
    scene = blocking(Scene(repo, tmp_path, real=True), "crap", "pass_through")
    scene.write(MOD, BIG)
    scene.write(TEST, CHECKS)
    repo.sh("add", "-A")
    repo.sh("commit", "-m", "a big function, fully tested")
    scene.write(MOD, SPLIT)

    outcome = run(scene)

    assert isinstance(result_of(outcome, "crap"), Approved)
    rejected = result_of(outcome, "pass_through")
    assert isinstance(rejected, Rejected)
    assert rejected.findings[0].target == f"{MOD}::big"
    assert outcome.verdict is Verdict.REJECTED  # type: ignore[attr-defined]


def test_characterization_tests_that_check_nothing_are_rejected_by_mutation(
    repo: Repo, tmp_path: Path
) -> None:
    scene = blocking(Scene(repo, tmp_path, real=True), "mutation")
    scene.write(TEST, "from sample.mod import add\n\n\ndef test_add() -> None:\n    add(1, 2)\n")
    repo.sh("add", "-A")
    repo.sh("commit", "-m", "characterization tests that run the code and check nothing")
    scene.write(MOD, "def add(a: int, b: int) -> int:\n    return b + a\n")

    outcome = run(scene)

    assert isinstance(result_of(outcome, "mutation"), Rejected)
    assert outcome.verdict is Verdict.REJECTED  # type: ignore[attr-defined]
