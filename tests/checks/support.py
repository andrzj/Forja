"""A small Python project in a real git repository, and the pieces to judge changes made to it."""

import sys
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any, cast

from forja.core.adapters import (
    AdapterRegistry,
    CommandPlan,
    Detection,
    EvidenceDraft,
    FileClass,
    LanguageAdapter,
    NotSupported,
    Operation,
    OperationRequest,
    Parsed,
    ParseResult,
    ToolOutput,
)
from forja.core.adapters.scoped import ScopedAdapter
from forja.core.events import EventLog
from forja.core.evidence import Target, TargetKind
from forja.core.gates import CheckSettings, InconclusivePolicy, Mode
from forja.core.process import ProcessIdentity
from forja.core.states import ExecutionState, Level
from forja.languages.python import PythonAdapter
from forja.orchestrator.measurer import PipelineMeasurer
from forja.orchestrator.ports import AttemptContext, TaskInfo
from tests.core.adapters.fakes import FakeLanguageAdapter
from tests.core.events.support import FakeClock
from tests.core.idempotency.conftest import Repo

FAKE_GITLEAKS = Path(__file__).with_name("fake_gitleaks.py")
FAKE_TOOLS = str(Path(__file__).with_name("fake_tools.py"))
LIZARD = (sys.executable, "-m", "lizard")
BLOCKING = CheckSettings(Mode.BLOCKING, InconclusivePolicy.BLOCK)
PREMISE = CheckSettings(Mode.BLOCKING, InconclusivePolicy.PREMISE)
OBSERVATION = CheckSettings(Mode.OBSERVATION, InconclusivePolicy.PREMISE)
RUN = "r1abcdef0123"

SAMPLE: Mapping[str, str] = {
    "pyproject.toml": (
        '[project]\nname = "sample"\nversion = "0"\n\n'
        "[tool.ruff]\nline-length = 100\n\n"
        '[tool.pytest.ini_options]\npythonpath = ["src"]\n'
    ),
    "src/sample/__init__.py": "",
    "src/sample/mod.py": "def add(a: int, b: int) -> int:\n    return a + b\n",
    "src/sample/other.py": "def twice(a: int) -> int:\n    return a * 2\n",
    "tests/test_mod.py": (
        "from sample.mod import add\n\n\ndef test_add() -> None:\n    assert add(1, 2) == 3\n"
    ),
}


def deep(name: str, branches: int) -> str:
    """A function with ``branches + 1`` as its cyclomatic complexity."""
    body = "".join(f"    if n == {i}:\n        return {i}\n" for i in range(branches))
    return f"def {name}(n: int) -> int:\n{body}    return -1\n"


def registry_of(*adapters: LanguageAdapter) -> AdapterRegistry:
    registry = AdapterRegistry()
    for adapter in adapters:
        registry.register_language(adapter)
    return registry


def projects_of(*adapters: LanguageAdapter) -> tuple[ScopedAdapter, ...]:
    """One project at the root for each adapter."""
    registry = registry_of(*adapters)
    return tuple(registry.project(a.language) for a in registry.languages())


class Run:
    """One process the pipeline started, as the runner announced it."""

    def __init__(
        self, where: tuple[Level, str, str], operation_id: str, details: Mapping[str, object]
    ) -> None:
        self.where = where
        self.operation_id = operation_id
        self.command: tuple[str, ...] = tuple(cast(Iterable[str], details["command"]))
        self.cwd = Path(str(details["cwd"]))
        self.timeout = details["timeout"]
        self.stdin_file = details["stdin_file"]
        self.env_names: tuple[str, ...] = tuple(cast(Iterable[str], details["env_names"]))

    @property
    def check(self) -> str:
        return self.operation_id.split(":")[-2]


class Recorder:
    """The sink factory of the pipeline in a test: remembers who asked and what ran."""

    def __init__(self) -> None:
        self.asked: list[tuple[Level, str, str]] = []
        self.runs: list[Run] = []

    def sinks(self, level: Level, target_id: str, operation: str) -> "RecordingSink":
        where = (level, target_id, operation)
        self.asked.append(where)
        return RecordingSink(self, where)

    def forget(self) -> None:
        self.asked.clear()
        self.runs.clear()


class RecordingSink:
    """Takes what the process runner reports; keeps the announcements of what it starts."""

    def __init__(
        self, recorder: Recorder | None = None, where: tuple[Level, str, str] | None = None
    ) -> None:
        self._recorder, self._where = recorder, where

    def intent(self, operation_id: str, details: Mapping[str, object]) -> None:
        if self._recorder is not None and self._where is not None:
            self._recorder.runs.append(Run(self._where, operation_id, details))

    def started(self, operation_id: str, identity: ProcessIdentity) -> None:
        pass

    def progress(self, operation_id: str, channel: str, line: str) -> None:
        pass

    def effect(self, operation_id: str, details: Mapping[str, object]) -> None:
        pass


def sinks(level: Level, target_id: str, operation: str) -> RecordingSink:
    return RecordingSink()


class Scene:
    """The sample project committed in ``repo``; edit its files, then judge the working tree."""

    def __init__(self, repo: Repo, work: Path, *, real: bool = False, **options: Any) -> None:
        self.repo, self.work = repo, work
        for relative, text in SAMPLE.items():
            self.write(relative, text)
        repo.sh("add", "-A")
        repo.sh("commit", "-m", "sample project")
        self.log = EventLog.open(work / "events.jsonl", RUN, clock=FakeClock())
        self.log.append_transition(Level.EXECUTION, RUN, None, ExecutionState.PREPARING)
        if real:
            self.adapter = PythonAdapter(cache_dir=work / "pycache")
            self.lizard = LIZARD
        else:
            fake = (sys.executable, FAKE_TOOLS)
            self.adapter = PythonAdapter(
                python=(*fake, "python"), ruff=(*fake, "ruff"), cache_dir=work / "pycache"
            )
            self.lizard = (*fake, "lizard")
        self.recorder = Recorder()
        self.measurer = self.make_measurer(**options)

    def make_measurer(
        self,
        *,
        settings: Mapping[str, CheckSettings] | None = None,
        gitleaks: tuple[str, ...] | None = None,
        values: Mapping[str, Mapping[str, Any]] | None = None,
        timeouts: Mapping[str, float] | None = None,
        workdir: Path | None = None,
        gate_10: Mapping[str, Any] | None = None,
    ) -> PipelineMeasurer:
        standard = {
            name: BLOCKING for name in ("scope", "secrets", "format", "lint", "build", "tests")
        } | {
            "complexity": PREMISE,
            "mutation": OBSERVATION,
            "crap": OBSERVATION,
            "pass_through": OBSERVATION,
            "module_depth": OBSERVATION,
            "sast": OBSERVATION,
            "dependency_audit": OBSERVATION,
            "new_dependency": OBSERVATION,
            "citations": OBSERVATION,
            "change_record": OBSERVATION,
            "readme": OBSERVATION,
            "doc_drift": OBSERVATION,
            "e2e": OBSERVATION,
            "test_data": OBSERVATION,
            "voice": OBSERVATION,
            "comments": OBSERVATION,
        }
        return PipelineMeasurer(
            adapters=registry_of(self.adapter),
            git=self.repo.git,
            log=self.log,
            workdir=workdir or self.work / "run",
            host_env=self.repo.env,
            settings=settings or standard,
            values=values,
            lizard=self.lizard,
            gitleaks=gitleaks or (sys.executable, str(FAKE_GITLEAKS)),
            timeouts=timeouts,
            **(gate_10 or {}),
        )

    def write(self, relative: str, text: str) -> None:
        target = self.repo.path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8", newline="\n")

    def context(
        self,
        scope: tuple[str, ...] = ("src/sample/mod.py",),
        max_files: int = 8,
        max_lines: int = 400,
    ) -> AttemptContext:
        task = TaskInfo("t1", "t1-s", "reduce the complexity", scope, max_files, max_lines)
        return AttemptContext(task, "t1-a1", self.repo.path, None)


def judge_with(scene: Scene, check: str) -> Any:
    """The result of one check of the pipeline for the current working tree."""
    import asyncio  # noqa: PLC0415

    outcome = asyncio.run(scene.measurer.judge(scene.context(), sinks))
    return next(run.result for run in outcome.runs if run.check_id == check)


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

    def detect(self, root: Path) -> Detection | None:
        """Present where a file named ``<language>.marker`` is."""
        marker = f"{self.language}.marker"
        return Detection(self.language, (".",), (marker,)) if (root / marker).is_file() else None

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


def draft(measurement: str, path: str, value: bool | int | float | str = 1) -> EvidenceDraft:
    return EvidenceDraft(measurement, Target(kind=TargetKind.FILE, id=path), value, "violations")
