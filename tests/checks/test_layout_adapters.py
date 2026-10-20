"""Format and lint over more than one language: each file goes to the adapter that claims it."""

import asyncio
import sys
from pathlib import Path

import pytest

from forja.checks.changes import Change, ChangeKind, Changes
from forja.checks.layout import FormatCheck, LintCheck
from forja.checks.tooling import Tools
from forja.core.adapters import (
    CommandPlan,
    EvidenceDraft,
    FileClass,
    NotSupported,
    Operation,
    OperationRequest,
    Parsed,
    ParseResult,
    ToolOutput,
)
from forja.core.events import EventLog
from forja.core.evidence import Target, TargetKind
from forja.core.gates import Approved, GateInput, NotApplicable, Rejected
from forja.core.states import ExecutionState, Level
from tests.checks.support import RUN, registry_of, sinks
from tests.core.adapters.fakes import FakeLanguageAdapter
from tests.core.events.support import FakeClock


class Stub(FakeLanguageAdapter):
    """Claims the files with one suffix; the tool it plans is a process that does nothing, and
    what it reads out of it is what the test says (the old text and the new text apart)."""

    def __init__(
        self,
        language: str,
        suffix: str,
        home: Path,
        *,
        after: tuple[EvidenceDraft, ...] = (),
        before: tuple[EvidenceDraft, ...] = (),
        offers: bool = True,
        offers_before: bool = True,
        config: tuple[str, ...] = (),
    ) -> None:
        self.language = language
        self.suffix = suffix
        self.home = home
        self.after, self.before = after, before
        self.offers, self.offers_before = offers, offers_before
        self.lint_config_files = config
        self.requests: list[OperationRequest] = []
        self.config_seen: list[bool] = []
        self._old = False

    def classify(self, path: str) -> FileClass | None:
        return FileClass.PRODUCTION if path.endswith(self.suffix) else None

    def plan(self, operation: Operation, request: OperationRequest) -> CommandPlan | NotSupported:
        self._old = request.root != self.home
        if not (self.offers_before if self._old else self.offers):
            return NotSupported(operation.value, "not offered")
        self.requests.append(request)
        if self._old:
            self.config_seen.append(
                all((request.root / c).is_file() for c in self.lint_config_files)
            )
        return CommandPlan((sys.executable, "-c", "pass"), request.root)

    def parse(self, operation: Operation, output: ToolOutput) -> ParseResult:
        return Parsed(self.before if self._old else self.after)


def draft(measurement: str, path: str, value: int = 1) -> EvidenceDraft:
    return EvidenceDraft(measurement, Target(kind=TargetKind.FILE, id=path), value, "violations")


def changes_of(*paths: str) -> Changes:
    return Changes(tuple(Change(ChangeKind.MODIFIED, p) for p in paths), 1, ())


def data() -> GateInput:
    return GateInput(Path("."), "c" * 40, "t1", "t1-s", "t1-a1")


@pytest.fixture
def tools(tmp_path: Path) -> Tools:
    log = EventLog.open(tmp_path / "events.jsonl", RUN, clock=FakeClock())
    log.append_transition(Level.EXECUTION, RUN, None, ExecutionState.PREPARING)
    return Tools(
        sinks=sinks,
        log=log,
        level=Level.ATTEMPT,
        target="t1-a1",
        logs=tmp_path / "logs",
        host_env={},
    )


def test_every_adapter_formats_its_own_files_and_the_findings_add_up(
    tools: Tools, tmp_path: Path
) -> None:
    py = Stub("python", ".py", tmp_path, after=(draft("format.diff", "a.py"),))
    go = Stub("go", ".go", tmp_path, after=(draft("format.diff", "b.go"),))
    check = FormatCheck(tools, registry_of(py, go), tmp_path, changes_of("a.py", "b.go", "c.md"))

    result = asyncio.run(check.evaluate(data()))

    assert isinstance(result, Rejected)
    assert sorted(f.target for f in result.findings) == ["a.py", "b.go"]
    assert [r.files for r in py.requests] == [("a.py",)]
    assert [r.files for r in go.requests] == [("b.go",)]


def test_an_adapter_without_a_formatter_leaves_its_files_and_the_others_still_count(
    tools: Tools, tmp_path: Path
) -> None:
    py = Stub("python", ".py", tmp_path, after=(draft("format.diff", "a.py"),))
    go = Stub("go", ".go", tmp_path, offers=False)

    result = asyncio.run(
        FormatCheck(tools, registry_of(py, go), tmp_path, changes_of("a.py", "b.go")).evaluate(
            data()
        )
    )
    assert isinstance(result, Rejected)

    nobody = asyncio.run(
        FormatCheck(
            tools,
            registry_of(Stub("go", ".go", tmp_path, offers=False)),
            tmp_path,
            changes_of("b.go"),
        ).evaluate(data())
    )
    assert nobody == NotApplicable(missing_capability="format")


def test_a_lint_violation_is_new_only_against_the_same_adapters_old_text(
    tools: Tools, tmp_path: Path
) -> None:
    py = Stub(
        "python",
        ".py",
        tmp_path,
        after=(draft("lint.E1", "a.py", 3),),
        before=(draft("lint.E1", "a.py", 3),),
    )
    go = Stub(
        "go",
        ".go",
        tmp_path,
        after=(draft("lint.errcheck", "b.go", 3),),
        before=(draft("lint.errcheck", "b.go", 1),),
    )
    check = LintCheck(
        tools,
        registry_of(py, go),
        tmp_path,
        changes_of("a.py", "b.go"),
        {"a.py": "x\n", "b.go": "y\n"},
    )

    result = asyncio.run(check.evaluate(data()))

    assert isinstance(result, Rejected)
    assert [(f.target, f.measured, f.limit) for f in result.findings] == [("b.go", 3, 1)]
    assert [sorted(r.files) for r in go.requests if r.root != tmp_path] == [["b.go"]]


def test_the_old_text_is_linted_with_the_config_its_adapter_names(
    tools: Tools, tmp_path: Path
) -> None:
    (tmp_path / "linter.toml").write_text("x\n", encoding="utf-8")
    py = Stub("python", ".py", tmp_path, config=("linter.toml",))
    check = LintCheck(tools, registry_of(py), tmp_path, changes_of("a.py"), {"a.py": "x\n"})

    assert asyncio.run(check.evaluate(data())) == Approved()
    assert py.config_seen == [True]


def test_a_linter_that_cannot_run_on_the_old_text_leaves_its_files_alone(
    tools: Tools, tmp_path: Path
) -> None:
    java = Stub(
        "java", ".java", tmp_path, after=(draft("lint.pmd", "A.java"),), offers_before=False
    )
    check = LintCheck(tools, registry_of(java), tmp_path, changes_of("A.java"), {"A.java": "x\n"})

    assert asyncio.run(check.evaluate(data())) == NotApplicable(missing_capability="lint")
