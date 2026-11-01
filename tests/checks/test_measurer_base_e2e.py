"""What the base's two end-to-end runs say: who is unstable, who passes, who fails, where."""

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from forja.checks import e2e as e2e_module
from forja.checks.e2e import E2ERun
from forja.orchestrator import measurer as measurer_module
from tests.checks.support import Scene
from tests.checks.test_gate_6_measurer import declared, scene_with
from tests.core.idempotency.conftest import Repo, repo  # noqa: F401 - re-exported as a fixture


def base_e2e(monkeypatch: pytest.MonkeyPatch, scene: Scene, runs: list[E2ERun | None]) -> Any:
    answers = iter(runs)

    async def scripted(*_args: Any) -> E2ERun | None:
        return next(answers)

    monkeypatch.setattr(measurer_module, "run_e2e", scripted)
    monkeypatch.setattr(e2e_module, "run_e2e", scripted)
    return asyncio.run(scene.measurer._base_e2e(None, scene.repo.path, ()))  # type: ignore[arg-type]


def test_the_two_runs_of_the_base_are_read_apart_test_by_test(
    repo: Repo,  # noqa: F811
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scene = scene_with(repo, tmp_path, e2e_commands=declared("pass"))
    first = E2ERun(
        {"a": "passed", "b": "passed", "c": "failed", "d": "passed", "e": "error", "f": "failed"},
        ("x", "y"),
    )
    second = E2ERun(
        {"a": "passed", "b": "failed", "c": "error", "d": "passed", "e": "passed", "g": "passed"},
        ("y", "z"),
    )

    base = base_e2e(monkeypatch, scene, [first, second])

    assert base.unstable == ("b", "c", "e", "f", "g")
    assert base.passing == ("a", "d")
    assert base.failing == ("c",)
    assert base.destinations == ("x", "y", "z")
    assert base.ran is True


def test_a_run_that_gave_no_answer_counts_as_one_with_no_tests(
    repo: Repo,  # noqa: F811
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scene = scene_with(repo, tmp_path, e2e_commands=declared("pass"))

    base = base_e2e(monkeypatch, scene, [E2ERun({"a": "passed"}, ()), None])

    assert (base.unstable, base.passing, base.failing, base.ran) == (("a",), (), (), True)


def test_the_base_metrics_are_saved_with_their_keys_in_order(
    repo: Repo,  # noqa: F811
    tmp_path: Path,
) -> None:
    scene = scene_with(repo, tmp_path)
    scene.write("src/sample/mod.py", "X = 1\n")

    asyncio.run(scene.measurer.baseline(scene.repo.path, scene.recorder.sinks))

    text = (scene.work / "run" / "base-metrics.json").read_text(encoding="utf-8")
    keys = list(json.loads(text))
    assert keys == sorted(keys)


def test_the_base_metrics_come_back_as_they_were_saved_and_none_when_unknown(
    repo: Repo,  # noqa: F811
    tmp_path: Path,
) -> None:
    scene = scene_with(repo, tmp_path)
    run = scene.work / "run"
    run.mkdir(parents=True, exist_ok=True)

    assert scene.measurer._read_base_metrics() == {}
    (run / "base-metrics.json").write_text('{"tests": 4, "unstable_tests": 0.5}', encoding="utf-8")

    assert scene.measurer._read_base_metrics() == {"tests": 4.0, "unstable_tests": 0.5}
