"""The lint of the old text runs in a private copy of the worktree: the real adapters plan it at
the root they are given, with their own tool, and nothing is read from anywhere else."""

from pathlib import Path

from forja.core.adapters import CommandPlan, Operation, OperationRequest
from forja.languages.python import PythonAdapter
from forja.languages.typescript import TypeScriptAdapter


def test_python_plans_the_lint_of_the_old_text_in_the_copy(tmp_path: Path) -> None:
    adapter = PythonAdapter(python=("py",), ruff=("rf",), cache_dir=tmp_path / "cache")
    copy = tmp_path / "copy"
    copy.mkdir()

    plan = adapter.plan(Operation.LINT, OperationRequest(root=copy, files=("a.py",)))

    assert isinstance(plan, CommandPlan)
    assert plan.cwd == copy
    assert plan.argv[:2] == ("rf", "check")
    assert plan.argv[-1] == "a.py"


def test_typescript_plans_the_lint_of_the_old_text_in_the_copy(tmp_path: Path) -> None:
    copy = tmp_path / "copy"
    copy.mkdir()
    (copy / "package.json").write_text('{"devDependencies": {"eslint": "9"}}', encoding="utf-8")

    plan = TypeScriptAdapter().plan(Operation.LINT, OperationRequest(root=copy, files=("a.ts",)))

    assert isinstance(plan, CommandPlan)
    assert plan.cwd == copy
    assert plan.argv[-1] == "a.ts"
