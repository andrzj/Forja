"""An extra test stage judges the code the implementer committed, read against what it was."""

import asyncio
from typing import Any

from forja.checks.changes import read_changes
from forja.checks.freeze import AppendOnlyCheck, FreezeCheck
from forja.core.artifacts.models import Producer
from forja.orchestrator.ports import AttemptContext, TaskInfo
from tests.checks.support import BLOCKING, OBSERVATION, PREMISE, Scene
from tests.checks.test_measurer import MOD, commit_mod
from tests.checks.test_precision import tail

MORE_TESTS = "def test_more() -> None:\n    assert True\n"


def extra_stage(scene: Scene) -> list[str]:
    """The implementer commits a change of ``mod.py`` and the test author adds a test file."""
    commit_mod(scene, MOD + "\n\nX = 1\n")
    scene.repo.sh("commit", "--amend", "-m", "the implementer's work\n\nStage-Id: t1-s")
    scene.write("tests/test_more.py", MORE_TESTS)
    task = TaskInfo(
        "t1",
        "t1-t2",
        "test what was written",
        (),
        8,
        400,
        role=Producer.TEST_AUTHOR,
        test_root="tests",
        attempt_prefix="t1-t2a",
        reviews="t1-s",
    )
    context = AttemptContext(task, "t1-t2a1", scene.repo.path, None)
    names = ("scope", "freeze", "secrets", "format", "lint", "build", "tests")
    scene.measurer = scene.make_measurer(
        settings={name: BLOCKING for name in names}
        | {
            "complexity": PREMISE,
            "mutation": OBSERVATION,
            "crap": OBSERVATION,
            "pass_through": OBSERVATION,
            "module_depth": OBSERVATION,
        }
    )
    asyncio.run(scene.measurer.judge(context, scene.recorder.sinks))
    return [f"{r.check}: {tail(r)}" for r in scene.recorder.runs]


def test_the_code_of_the_implementer_is_measured_after_and_before_its_stage(scene: Scene) -> None:
    ran = extra_stage(scene)

    assert ran.count("complexity: ('--csv', '--', 'src/sample/mod.py')") == 4  # twice per gate
    assert tail_of(scene, "lint")[-1] == "tests/test_more.py"  # lint reads only the new tests


def tail_of(scene: Scene, check: str) -> tuple[str, ...]:
    (found,) = [r for r in scene.recorder.runs if r.check == check]
    return tail(found)


def kinds(scene: Scene, **task: Any) -> list[type]:
    info = TaskInfo("t1", "t1-s", "x", (), 8, 400, **task)
    context = AttemptContext(info, "t1-a1", scene.repo.path, None)
    changes = asyncio.run(read_changes(scene.repo.git))
    return [type(check) for check in asyncio.run(scene.measurer._frozen(context, changes))]


def test_a_stage_that_only_adds_tests_is_judged_by_what_it_added(scene: Scene) -> None:
    assert kinds(scene, test_root="tests", reviews="t1-s") == [AppendOnlyCheck]


def test_the_implementer_is_judged_by_what_the_test_author_froze(scene: Scene) -> None:
    assert kinds(scene, test_root="tests", frozen_digest="abc") == [FreezeCheck]


def test_tests_beside_the_code_are_held_without_a_tests_root(scene: Scene) -> None:
    assert kinds(scene, reviews="t1-s") == [AppendOnlyCheck]
    assert kinds(scene, frozen_digest="abc") == [FreezeCheck]


def test_nothing_is_checked_without_a_digest_to_hold_the_tests_to(scene: Scene) -> None:
    assert kinds(scene, test_root="tests") == []
