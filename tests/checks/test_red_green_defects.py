"""The red gate on the planted-defect repositories: reference tests pass it, bad ones do not."""

import asyncio
import json
import re
import shutil
from pathlib import Path
from typing import Any

import pytest

from forja.checks.red_green import RedGreenCheck
from forja.core.adapters import FileClass
from forja.core.artifacts.llm_output import DeclaredTest
from forja.core.events import EventLog
from forja.core.gates import Approved, Rejected
from forja.core.states import ExecutionState, Level
from forja.languages.python import PythonAdapter
from tests.checks.support import RUN
from tests.checks.test_units import data, tools
from tests.core.events.support import FakeClock

pytestmark = pytest.mark.integration

DEFECTS = Path(__file__).resolve().parents[2] / "scripts" / "medicao" / "defeitos"
NAMES = ("pager", "spans", "money", "slugs")
ADAPTER = PythonAdapter()


@pytest.fixture
def log(tmp_path: Path) -> EventLog:
    opened = EventLog.open(tmp_path / "events.jsonl", RUN, clock=FakeClock())
    opened.append_transition(Level.EXECUTION, RUN, None, ExecutionState.PREPARING)
    return opened


def classify(path: str) -> FileClass:
    return ADAPTER.classify(path) or FileClass.OTHER


def worktree(tmp_path: Path, name: str, *, fixed: bool, test: Path) -> str:
    work = tmp_path / "work"
    shutil.copytree(DEFECTS / name / "repo", work)
    if fixed:
        shutil.copy(DEFECTS / name / "corrigido" / "core.py", work / "src" / name / "core.py")
    shutil.copy(test, work / "tests" / test.name)
    return f"tests/{test.name}"


def judge(
    log: EventLog,
    tmp_path: Path,
    name: str,
    test: Path,
    *,
    fixed: bool = False,
    only_first: bool = False,
) -> Any:
    path = worktree(tmp_path, name, fixed=fixed, test=test)
    criteria = json.loads((DEFECTS / name / "criterios.json").read_text(encoding="utf-8"))
    ids = frozenset(int(c["id"]) for c in criteria["criteria"])
    if only_first:
        ids = frozenset({1})
    functions = re.findall(r"^def (test_\w+)", test.read_text(encoding="utf-8"), re.MULTILINE)
    # the first test stands for criterion 1, and the rest for the other criteria in order
    declared = tuple(
        DeclaredTest(criterion_id=n, test_id=f"{path}::{function}", path=path)
        for n, function in zip(sorted(ids), functions, strict=False)
    )
    check = RedGreenCheck(tools(log, tmp_path), ADAPTER, tmp_path / "work", classify, ids, declared)
    return asyncio.run(check.evaluate(data()))


@pytest.mark.parametrize("name", NAMES)
def test_the_reference_tests_are_red_on_the_defect(
    log: EventLog, tmp_path: Path, name: str
) -> None:
    reference = DEFECTS / name / "referencia" / "test_referencia.py"

    assert judge(log, tmp_path, name, reference) == Approved()


@pytest.mark.parametrize("name", NAMES)
def test_the_reference_tests_are_rejected_once_the_defect_is_fixed(
    log: EventLog, tmp_path: Path, name: str
) -> None:
    reference = DEFECTS / name / "referencia" / "test_referencia.py"

    result = judge(log, tmp_path, name, reference, fixed=True)

    assert isinstance(result, Rejected)
    assert all("passes on the code with the defect" in f.message for f in result.findings)


@pytest.mark.parametrize(
    "bad", sorted(DEFECTS.glob("*/ruins/test_ruim_*.py")), ids=lambda p: f"{p.parts[-3]}-{p.stem}"
)
def test_every_bad_test_is_rejected(log: EventLog, tmp_path: Path, bad: Path) -> None:
    result = judge(log, tmp_path, bad.parts[-3], bad, only_first=True)

    assert isinstance(result, Rejected)
    cause = "errors out" if "importacao" in bad.stem else "passes on the code with the defect"
    assert [f.message for f in result.findings if cause not in f.message] == []
    assert result.findings
