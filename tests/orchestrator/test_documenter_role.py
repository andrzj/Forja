"""The documenter: its place in the plan, its package, its scope and what counts as a document."""

import asyncio
from pathlib import Path

import pytest

from forja.checks.changes import Change, ChangeKind, Changes
from forja.checks.scope import ScopeCheck
from forja.core.adapters import AdapterRegistry, FileClass
from forja.core.adapters.language import is_documentation
from forja.core.artifacts.models import Producer
from forja.core.gates import Approved, GateInput, Rejected
from forja.core.redaction import Redactor
from forja.languages.python import PythonAdapter
from forja.orchestrator.agent_runner import build_package
from forja.orchestrator.config import Budget, FixRequest
from forja.orchestrator.planner import ComplexityPlanner, FixPlanner
from forja.orchestrator.ports import AttemptContext, Baseline, TaskInfo


@pytest.mark.parametrize(
    "path",
    ["README.md", "readme", "README.rst", "docs/adr/0001-x.md", "sub/CHANGELOG.md", "Docs/a.txt"],
)
def test_these_are_documents(path: str) -> None:
    assert is_documentation(path)


@pytest.mark.parametrize(
    "path", ["src/a.py", "docsrc/a.py", "src/docs.py", "notes.txt", "a/b.json"]
)
def test_these_are_not(path: str) -> None:
    assert not is_documentation(path)


def test_a_file_no_language_claims_is_a_document_or_other() -> None:
    registry = AdapterRegistry()
    registry.register_language(PythonAdapter())
    assert registry.classify("README.md") is FileClass.DOCUMENTATION
    assert registry.classify("docs/guide.md") is FileClass.DOCUMENTATION
    assert registry.classify("src/a.py") is FileClass.PRODUCTION
    assert registry.classify("package-lock.json") is FileClass.OTHER


def test_every_refactoring_and_fix_task_ends_with_the_documenter() -> None:
    async def functions(worktree: Path) -> dict[tuple[str, str], int]:
        return {("src/a.py", "f"): 30}

    refactor = asyncio.run(ComplexityPlanner(functions).plan(Path("."), Baseline(True), Budget()))
    fix = FixRequest.model_validate(
        {
            "description": "d",
            "criteria": {"criteria": [{"id": 1, "text": "t", "level": "unit", "origin": "x"}]},
        }
    )
    fixing = asyncio.run(FixPlanner(fix, ("src",)).plan(Path("."), Baseline(True), Budget()))

    assert refactor[0].stages == (Producer.IMPLEMENTER, Producer.DOCUMENTER)
    assert fixing[0].stages == (Producer.TEST_AUTHOR, Producer.IMPLEMENTER, Producer.DOCUMENTER)


def documenter_task() -> TaskInfo:
    return TaskInfo("t1", "t1-d", "reduce f", ("src/a.py",), 3, 120, Producer.DOCUMENTER)


def judge(*paths: str, lines: int = 3000) -> object:
    changes = Changes(tuple(Change(ChangeKind.MODIFIED, p) for p in paths), lines, ())
    classify = AdapterRegistry()
    classify.register_language(PythonAdapter())
    data = GateInput(Path("."), "c" * 40, "t1", "t1-d", "t1-da1")
    return asyncio.run(ScopeCheck(changes, documenter_task(), classify.classify).evaluate(data))


def test_the_documenter_may_change_documents_whatever_their_size_and_place() -> None:
    assert isinstance(judge("README.md", "docs/mudancas/t1.md", "docs/adr/0026-x.md"), Approved)


def test_the_documenter_may_not_change_code_tests_or_configuration() -> None:
    result = judge("src/a.py", "tests/test_a.py", "pyproject.toml")
    assert isinstance(result, Rejected)
    assert [f.target for f in result.findings] == ["src/a.py", "tests/test_a.py", "pyproject.toml"]
    said = "the documenter may change only documentation (this is {})"
    assert [f.message for f in result.findings] == [
        said.format("production"),
        said.format("test"),
        said.format("other"),
    ]


def test_the_package_of_the_documenter_says_what_it_may_do_and_how_to_answer(
    tmp_path: Path,
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    ctx = AttemptContext(documenter_task(), "t1-da1", tmp_path, None)

    text = build_package(ctx, Redactor())

    assert "You are documenting a change that is already made and approved." in text
    assert "Only documentation files." in text
    assert "You cannot run commands" in text
    assert "Forja writes it from your" in text
    assert '"claims"' in text
    assert "### `src/a.py`" in text
    assert "You are refactoring" not in text
