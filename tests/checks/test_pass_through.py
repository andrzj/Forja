"""The pass-through check: only functions the attempt made into mere forwarders are reproved."""

import asyncio
from pathlib import Path

from forja.checks.changes import read_before, read_changes
from forja.checks.pass_through import PassThroughCheck
from forja.core.gates import GateInput
from forja.core.gates.models import Approved, GateResult, Inconclusive, Rejected
from tests.checks.support import Scene

MOD = "src/sample/mod.py"
FORWARD = "def hop(a, b):\n    return real(a, b)\n\n\ndef real(a, b):\n    return a + b\n"


def judge(scene: Scene, files: tuple[str, ...] = (MOD,)) -> GateResult:
    git = scene.repo.git.at(scene.repo.path)
    changes = asyncio.run(read_changes(git))
    before = asyncio.run(read_before(git, changes, (".py", ".go", ".ts")))
    check = PassThroughCheck(scene.repo.path, changes, files, before)
    data = GateInput(Path("."), "c" * 40, "t", "s", "a")
    return asyncio.run(check.evaluate(data))


def test_a_new_function_that_only_passes_its_arguments_on_is_rejected(scene: Scene) -> None:
    scene.write(MOD, FORWARD)

    result = judge(scene)

    assert isinstance(result, Rejected)
    (finding,) = result.findings
    assert finding.target == f"{MOD}::hop"


def test_a_function_that_does_work_of_its_own_is_approved(scene: Scene) -> None:
    scene.write(
        MOD, "def add(a, b):\n    return real(a, b) + 1\n\n\ndef real(a, b):\n    return a\n"
    )

    assert isinstance(judge(scene), Approved)


def test_an_old_forwarder_the_attempt_did_not_touch_is_not_reproved(scene: Scene) -> None:
    scene.write(MOD, FORWARD)
    scene.repo.sh("add", "-A")
    scene.repo.sh("commit", "-m", "old debt")
    scene.write(MOD, FORWARD + "\n\nX = 1\n")

    assert isinstance(judge(scene), Approved)


def test_a_function_that_became_a_forwarder_is_reproved(scene: Scene) -> None:
    scene.write(
        MOD, "def hop(a, b):\n    return real(a, b) + 1\n\n\ndef real(a, b):\n    return a\n"
    )
    scene.repo.sh("add", "-A")
    scene.repo.sh("commit", "-m", "base")
    scene.write(MOD, FORWARD)

    assert isinstance(judge(scene), Rejected)


def test_other_languages_are_read_too(scene: Scene) -> None:
    scene.write("pkg/a.go", "package p\n\nfunc Hop(a int) int { return Real(a) }\n")

    result = judge(scene, ("pkg/a.go",))

    assert isinstance(result, Rejected)
    assert result.findings[0].target == "pkg/a.go::Hop"


def test_no_production_files_and_unknown_languages_are_approved(scene: Scene) -> None:
    scene.write("notes.txt", "def hop(a):\n    return real(a)\n")

    assert isinstance(judge(scene, ()), Approved)
    assert isinstance(judge(scene, ("notes.txt",)), Approved)


def test_a_file_that_does_not_parse_is_inconclusive_not_approved(scene: Scene) -> None:
    scene.write(MOD, "def broken(:\n")

    assert isinstance(judge(scene), Inconclusive)
