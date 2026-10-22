"""The pipeline over a repository with several projects: each file goes to the project that owns
it, and what a project's tools write is read from the project's directory."""

import asyncio
import sys
from pathlib import Path

from forja.checks.coverage import CoverageShare, run_coverage
from forja.checks.layout import by_adapter, owned_by
from forja.checks.tooling import Tools
from forja.core.adapters import CommandPlan, NotSupported, Operation, OperationRequest
from forja.core.events import EventLog
from forja.core.gates import GateInput
from forja.core.reports import ReportFormat, ReportSpec
from forja.core.states import ExecutionState, Level
from forja.orchestrator.measurer import PipelineMeasurer
from tests.checks.support import RUN, Stub, registry_of, sinks
from tests.core.events.support import FakeClock

WRITE_REPORT = (
    "import json;"
    "json.dump({'files': {'src/a.py': {'executed_lines': [1, 2], 'missing_lines': [3]}}},"
    " open('cov.json', 'w'))"
)


class Covering(Stub):
    """Runs a process in the root it is given that writes a coverage report there."""

    def plan(self, operation: Operation, request: OperationRequest) -> CommandPlan | NotSupported:
        return CommandPlan((sys.executable, "-c", WRITE_REPORT), request.root)

    def report(self, operation: Operation) -> ReportSpec:
        return ReportSpec(ReportFormat.COVERAGE_PY_JSON, "cov.json", ("src",))


def _measurer(tmp_path: Path, *adapters: Stub) -> PipelineMeasurer:
    return PipelineMeasurer(
        adapters=registry_of(*adapters),
        git=None,  # type: ignore[arg-type]
        log=None,  # type: ignore[arg-type]
        workdir=tmp_path,
        host_env={},
        settings={},
        lizard=("lizard",),
    )


def _mark(root: Path, *directories: str, language: str = "python") -> None:
    for directory in directories:
        (root / directory).mkdir(parents=True, exist_ok=True)
        (root / directory / f"{language}.marker").write_text("", encoding="utf-8")


def test_one_project_per_manifest_directory_and_each_file_goes_to_the_deepest(
    tmp_path: Path,
) -> None:
    _mark(tmp_path, ".", "web", "web/ui")
    measurer = _measurer(tmp_path, Stub("python", ".py", tmp_path))

    active = measurer._active(tmp_path)

    assert [p.base for p in active] == [".", "web", "web/ui"]
    files = ("a.py", "web/b.py", "web/ui/c.py", "web/ui/d.py")
    assert [measurer._files_of(active, p, files) for p in active] == [
        ("a.py",),
        ("web/b.py",),
        ("web/ui/c.py", "web/ui/d.py"),
    ]
    assert measurer._texts_of(active, active[1], {"web/b.py": "x", "a.py": "y"}) == {
        "web/b.py": "x"
    }


def test_a_language_with_no_project_holding_a_changed_file_gets_one_at_the_root(
    tmp_path: Path,
) -> None:
    _mark(tmp_path, "api")
    measurer = _measurer(tmp_path, Stub("python", ".py", tmp_path), Stub("go", ".go", tmp_path))

    active = measurer._active(tmp_path, ("api/x.py", "svc/main.go", "svc/other.go"))

    assert [(p.language, p.base) for p in active] == [("python", "api"), ("go", ".")]


def test_a_repository_with_no_manifest_runs_the_first_language_at_the_root(tmp_path: Path) -> None:
    measurer = _measurer(tmp_path, Stub("python", ".py", tmp_path), Stub("go", ".go", tmp_path))

    assert [(p.language, p.base) for p in measurer._active(tmp_path)] == [("python", ".")]


def test_lint_and_format_group_the_files_by_the_project_that_owns_them(tmp_path: Path) -> None:
    _mark(tmp_path, "a", "b")
    measurer = _measurer(tmp_path, Stub("python", ".py", tmp_path))
    active = measurer._active(tmp_path)

    groups = by_adapter(active, ("b/x.py", "a/y.py", "b/z.py", "README.md"))

    assert [(p.base, files) for p, files in groups] == [
        ("b", ("b/x.py", "b/z.py")),
        ("a", ("a/y.py",)),
    ]
    assert not owned_by(active)("README.md") and owned_by(active)("a/y.py")


def test_the_coverage_of_a_project_is_read_from_its_directory_and_named_by_the_repository(
    tmp_path: Path,
) -> None:
    _mark(tmp_path, "web")
    (tmp_path / "web" / "src").mkdir()
    (tmp_path / "web" / "src" / "a.py").write_text("x\n", encoding="utf-8")
    project = registry_of(Covering("python", ".py", tmp_path)).project("python", "web")
    log = EventLog.open(tmp_path / "events.jsonl", RUN, clock=FakeClock())
    log.append_transition(Level.EXECUTION, RUN, None, ExecutionState.PREPARING)
    tools = Tools(
        sinks=sinks,
        log=log,
        level=Level.ATTEMPT,
        target="t1-a1",
        logs=tmp_path / "logs",
        host_env={},
    )
    data = GateInput(tmp_path, "c" * 40, "t1", "t1-s", "t1-a1")
    share = CoverageShare()

    report = asyncio.run(run_coverage(tools, project, tmp_path, data, share))

    assert list(report.files) == ["web/src/a.py"]
    assert report.files["web/src/a.py"].covered == frozenset({1, 2})
    assert share.report is report
    assert not (tmp_path / "web" / "cov.json").exists()
