"""What the pipeline reads of a Go project that lives in a directory of the repository: its
``go.mod``, the files that are its own, and the graph of its packages."""

import asyncio
import sys
from pathlib import Path

from forja.checks.architecture.compare import Snapshot
from forja.checks.changes import Change, ChangeKind, Changes
from forja.checks.tooling import Tools
from forja.core.adapters import (
    CommandPlan,
    FileClass,
    NotSupported,
    Operation,
    ToolInfo,
    VersionProbe,
)
from forja.core.adapters.scoped import ScopedAdapter
from forja.core.artifacts.schemas import ToolVersion
from forja.core.events import EventLog
from forja.core.states import ExecutionState, Level
from forja.orchestrator.measurer import PipelineMeasurer
from tests.checks.support import RUN, Recorder, Stub, registry_of
from tests.core.events.support import FakeClock

GO_MOD = "module example.com/m\n\ngo 1.22\n"
OLD_GO_MOD = "module example.com/old\n\ngo 1.21\n"
A_USES_B = 'package a\n\nimport "example.com/m/b"\n\nfunc F() { b.G() }\n'
B_PLAIN = "package b\n\nfunc G() {}\n"
B_USES_A = 'package b\n\nimport "example.com/m/a"\n\nfunc G() { a.F() }\n'


class Language(Stub):
    """Every file is production but the Go tests; Markdown is production too, to be turned away
    by the dialect and not by the class."""

    def classify(self, path: str) -> FileClass | None:
        return FileClass.TEST if path.endswith("_test.go") else FileClass.PRODUCTION


class Listing:
    """The git of a measurer that is asked only for the tracked files."""

    def __init__(self, tracked: list[str]) -> None:
        self.tracked = tracked

    def at(self, worktree: Path) -> "Listing":
        return self

    async def lines(self, *args: str) -> list[str]:
        assert args == ("ls-files",)
        return self.tracked


def _measurer(tmp_path: Path, git: object = None) -> PipelineMeasurer:
    return PipelineMeasurer(
        adapters=registry_of(Language("go", "", tmp_path)),
        git=git,  # type: ignore[arg-type]
        log=None,  # type: ignore[arg-type]
        workdir=tmp_path,
        host_env={},
        settings={},
        lizard=("lizard",),
    )


def _projects(tmp_path: Path, *bases: str) -> tuple[ScopedAdapter, ...]:
    registry = registry_of(Language("go", "", tmp_path))
    return tuple(registry.project("go", base) for base in bases)


def _write(root: Path, files: dict[str, str]) -> None:
    for relative, text in files.items():
        (root / relative).parent.mkdir(parents=True, exist_ok=True)
        (root / relative).write_text(text, encoding="utf-8", newline="\n")


def _changes(*files: Change) -> Changes:
    return Changes(files, 0, ())


def test_the_graph_of_a_go_project_in_a_directory_is_read_with_the_go_mod_of_that_directory(
    tmp_path: Path,
) -> None:
    _write(tmp_path, {"svc/go.mod": GO_MOD, "svc/a/a.go": A_USES_B, "svc/b/b.go": B_PLAIN})
    tracked = ["svc/go.mod", "svc/a/a.go", "svc/b/b.go"]
    active = _projects(tmp_path, "svc")

    found = asyncio.run(
        _measurer(tmp_path, Listing(tracked))._architecture_metrics(tmp_path, active)
    )

    assert found == {
        "dependency_cycles[svc]": 0.0,
        "dependency_edges[svc]": 1.0,
        "max_distance[svc]": 1.0,
    }


def test_a_go_project_whose_go_mod_is_not_in_its_directory_has_no_graph(tmp_path: Path) -> None:
    _write(tmp_path, {"go.mod": GO_MOD, "svc/a/a.go": A_USES_B, "svc/b/b.go": B_PLAIN})
    tracked = ["go.mod", "svc/a/a.go", "svc/b/b.go"]
    active = _projects(tmp_path, "svc")

    found = asyncio.run(
        _measurer(tmp_path, Listing(tracked))._architecture_metrics(tmp_path, active)
    )

    assert found == {}


def test_a_cycle_between_two_packages_of_a_go_project_at_the_root_is_counted_with_no_suffix(
    tmp_path: Path,
) -> None:
    _write(tmp_path, {"go.mod": GO_MOD, "a/a.go": A_USES_B, "b/b.go": B_USES_A})
    tracked = ["go.mod", "a/a.go", "b/b.go"]
    active = _projects(tmp_path, ".")

    found = asyncio.run(
        _measurer(tmp_path, Listing(tracked))._architecture_metrics(tmp_path, active)
    )

    assert found["dependency_cycles"] == 1.0
    assert found["dependency_edges"] == 2.0
    assert set(found) == {"dependency_cycles", "dependency_edges", "max_distance"}


def test_each_project_of_the_repository_reads_only_the_files_it_owns(tmp_path: Path) -> None:
    _write(
        tmp_path,
        {
            "go.mod": GO_MOD,
            "a/a.go": A_USES_B,
            "b/b.go": B_PLAIN,
            "svc/go.mod": "module example.com/svc\n\ngo 1.22\n",
            "svc/x/x.go": "package x\n\nfunc X() {}\n",
        },
    )
    tracked = ["go.mod", "a/a.go", "b/b.go", "svc/go.mod", "svc/x/x.go"]
    active = _projects(tmp_path, ".", "svc")

    found = asyncio.run(
        _measurer(tmp_path, Listing(tracked))._architecture_metrics(tmp_path, active)
    )

    assert found["dependency_edges"] == 1.0
    assert found["dependency_edges[svc]"] == 0.0


def _states(
    tmp_path: Path,
    changes: Changes,
    was: dict[str, str],
    tracked: list[str],
    *,
    bases: tuple[str, ...] = (".", "svc"),
    project: int = 1,
) -> tuple[Snapshot, Snapshot, tuple[str, ...]]:
    active = _projects(tmp_path, *bases)
    return _measurer(tmp_path)._project_states(
        tmp_path, changes, was, tracked, active, active[project]
    )


def test_a_project_the_attempt_left_alone_has_nothing_to_read(tmp_path: Path) -> None:
    _write(tmp_path, {"main.go": "package main\n", "svc/go.mod": GO_MOD})
    changes = _changes(Change(ChangeKind.MODIFIED, "main.go"))

    before, after, changed = _states(tmp_path, changes, {}, ["main.go", "svc/go.mod"])

    assert (before, after, changed) == (Snapshot("go", {}), Snapshot("go", {}), ())


def test_the_files_changed_are_the_production_code_of_the_project_in_a_language_the_forja_reads(
    tmp_path: Path,
) -> None:
    _write(tmp_path, {"svc/go.mod": GO_MOD, "svc/a/a.go": A_USES_B})
    changes = _changes(
        Change(ChangeKind.MODIFIED, "svc/a/a.go"),
        Change(ChangeKind.MODIFIED, "svc/a/a_test.go"),
        Change(ChangeKind.MODIFIED, "svc/README.md"),
        Change(ChangeKind.MODIFIED, "main.go"),
    )

    _, _, changed = _states(tmp_path, changes, {}, ["svc/a/a.go"])

    assert changed == ("a/a.go",)


def test_the_state_before_is_the_untouched_files_and_the_old_text_of_the_touched_ones(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        {
            "svc/go.mod": GO_MOD,
            "svc/a/a.go": A_USES_B,
            "svc/b/new.go": B_PLAIN,
            "svc/c/c.go": "package c\n",
            "main.go": "package main\n",
        },
    )
    changes = _changes(
        Change(ChangeKind.MODIFIED, "svc/a/a.go"),
        Change(ChangeKind.RENAMED, "svc/b/new.go", "svc/b/old.go"),
        Change(ChangeKind.DELETED, "svc/d/d.go"),
        Change(ChangeKind.DELETED, "svc/e/e.go"),
        Change(ChangeKind.DELETED, "other/f.go"),
        Change(ChangeKind.ADDED, "svc/g/g.go"),
    )
    was = {
        "svc/a/a.go": "package a // before\n",
        "svc/b/old.go": "package b // old\n",
        "svc/d/d.go": "package d // gone\n",
        "other/f.go": "package f // elsewhere\n",
        "svc/g/g.go": "package g // never there\n",
    }
    tracked = ["svc/go.mod", "svc/a/a.go", "svc/b/new.go", "svc/c/c.go", "main.go"]

    before, after, changed = _states(tmp_path, changes, was, tracked)

    assert before.files == {
        "a/a.go": "package a // before\n",
        "b/old.go": "package b // old\n",
        "c/c.go": "package c\n",
        "d/d.go": "package d // gone\n",
    }
    assert after.files == {
        "a/a.go": A_USES_B,
        "b/new.go": B_PLAIN,
        "c/c.go": "package c\n",
    }
    assert changed == ("a/a.go", "b/new.go", "g/g.go")


def test_a_go_project_carries_the_go_mod_it_had_and_the_one_it_has(tmp_path: Path) -> None:
    _write(tmp_path, {"svc/go.mod": GO_MOD, "svc/a/a.go": A_USES_B})
    changes = _changes(Change(ChangeKind.MODIFIED, "svc/a/a.go"))
    was = {"svc/go.mod": OLD_GO_MOD}

    before, after, _ = _states(tmp_path, changes, was, ["svc/go.mod", "svc/a/a.go"])
    same_before, same_after, _ = _states(tmp_path, changes, {}, ["svc/go.mod", "svc/a/a.go"])

    assert (before.go_mod, after.go_mod) == (OLD_GO_MOD, GO_MOD)
    assert (same_before.go_mod, same_after.go_mod) == (GO_MOD, GO_MOD)


def test_a_go_mod_is_looked_for_in_the_directory_of_a_go_project_only(tmp_path: Path) -> None:
    _write(tmp_path, {"go.mod": GO_MOD, "svc/a/a.go": A_USES_B})
    changes = _changes(Change(ChangeKind.MODIFIED, "svc/a/a.go"))

    before, after, _ = _states(tmp_path, changes, {"go.mod": OLD_GO_MOD}, ["svc/a/a.go"])

    assert (before.go_mod, after.go_mod) == (None, None)


class Elsewhere(Language):
    """The same stub, but of a language that has no ``go.mod``."""


def test_a_project_of_another_language_has_no_go_mod(tmp_path: Path) -> None:
    _write(tmp_path, {"go.mod": GO_MOD, "a/a.go": A_USES_B})
    registry = registry_of(Elsewhere("python", "", tmp_path))
    active = (registry.project("python"),)
    changes = _changes(Change(ChangeKind.MODIFIED, "a/a.go"))

    before, after, _ = _measurer(tmp_path)._project_states(
        tmp_path, changes, {"go.mod": OLD_GO_MOD}, ["go.mod", "a/a.go"], active, active[0]
    )

    assert (before.go_mod, after.go_mod) == (None, None)


class Probing(Stub):
    """A language whose toolchain answers with the version it is told to, or has none."""

    def __init__(self, language: str, home: Path, toolchain: str, says: str | None) -> None:
        super().__init__(language, "", home)
        self.toolchain, self.says = toolchain, says

    def tool_info(self, operation: Operation) -> ToolInfo | NotSupported:
        if self.says is None:
            return NotSupported(operation.value)
        plan = CommandPlan((sys.executable, "-c", f"print({self.says!r})"), self.home)
        probe = VersionProbe(plan, r"version (\d+\.\d+\.\d+)")
        return ToolInfo(self.language, probe, self.toolchain, probe)


def _tools(tmp_path: Path, recorder: Recorder) -> Tools:
    log = EventLog.open(tmp_path / "events.jsonl", RUN, clock=FakeClock())
    log.append_transition(Level.EXECUTION, RUN, None, ExecutionState.PREPARING)
    return Tools(
        sinks=recorder.sinks,
        log=log,
        level=Level.ATTEMPT,
        target="t1-a1",
        logs=tmp_path / "logs",
        host_env={},
    )


def test_the_toolchains_are_the_versions_each_language_reports_once_and_by_name(
    tmp_path: Path,
) -> None:
    for directory, language in (
        ("a", "go"),
        ("b", "go"),
        (".", "java"),
        (".", "csharp"),
        (".", "typescript"),
    ):
        (tmp_path / directory).mkdir(exist_ok=True)
        (tmp_path / directory / f"{language}.marker").write_text("", encoding="utf-8")
    measurer = PipelineMeasurer(
        adapters=registry_of(
            Probing("java", tmp_path, "java", "version 0.13.0"),
            Probing("go", tmp_path, "go", "go version 1.22.3"),
            Probing("csharp", tmp_path, "csharp", "nothing to say"),
            Probing("typescript", tmp_path, "typescript", None),
        ),
        git=None,  # type: ignore[arg-type]
        log=None,  # type: ignore[arg-type]
        workdir=tmp_path,
        host_env={},
        settings={},
        lizard=("lizard",),
    )
    recorder = Recorder()

    found = asyncio.run(measurer._toolchains(_tools(tmp_path, recorder), tmp_path))

    assert found == (
        ToolVersion(name="go", version="1.22.3"),
        ToolVersion(name="java", version="0.13.0"),
    )
    assert len(recorder.runs) == 3
