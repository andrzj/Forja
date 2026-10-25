"""The specifier writes no file: any change is rejected, and no change at all is what it owes."""

import asyncio
from pathlib import Path

from forja.checks.changes import Change, ChangeKind, Changes
from forja.checks.scope import ScopeCheck
from forja.core.adapters import AdapterRegistry
from forja.core.artifacts.models import Producer
from forja.core.gates import Approved, GateInput, Rejected
from forja.languages.python import PythonAdapter
from forja.orchestrator.ports import TaskInfo


def judge(*paths: str) -> object:
    registry = AdapterRegistry()
    registry.register_language(PythonAdapter())
    changes = Changes(tuple(Change(ChangeKind.MODIFIED, p) for p in paths), 3, ())
    task = TaskInfo("t1", "t1-c", "page 1 is wrong", ("src",), 8, 400, Producer.SPECIFIER)
    data = GateInput(Path("."), "c" * 40, "t1", "t1-c", "t1-ca1")
    return asyncio.run(ScopeCheck(changes, task, registry.classify).evaluate(data))


def test_a_specifier_that_changed_nothing_is_approved() -> None:
    assert isinstance(judge(), Approved)


def test_a_specifier_that_changed_a_file_of_any_kind_is_rejected() -> None:
    result = judge("src/a.py", "tests/test_a.py", "README.md", "docs/criteria.md")
    assert isinstance(result, Rejected)
    assert [f.target for f in result.findings] == [
        "src/a.py",
        "tests/test_a.py",
        "README.md",
        "docs/criteria.md",
    ]
    assert {f.message for f in result.findings} == {"the specifier writes criteria, not files"}


def test_an_archaeologist_that_changed_nothing_is_approved_and_one_that_wrote_a_file_is_not() -> (
    None
):
    def judge_archaeologist(*paths: str) -> object:
        registry = AdapterRegistry()
        registry.register_language(PythonAdapter())
        changes = Changes(tuple(Change(ChangeKind.MODIFIED, p) for p in paths), 3, ())
        task = TaskInfo("t1", "t1-f", "how?", ("src",), 8, 400, Producer.ARCHAEOLOGIST)
        data = GateInput(Path("."), "c" * 40, "t1", "t1-f", "t1-fa1")
        return asyncio.run(ScopeCheck(changes, task, registry.classify).evaluate(data))

    assert isinstance(judge_archaeologist(), Approved)
    result = judge_archaeologist("src/a.py", "docs/notes.md")
    assert isinstance(result, Rejected)
    assert {f.message for f in result.findings} == {"the archaeologist writes findings, not files"}
