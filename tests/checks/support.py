"""A small Python project in a real git repository, and the pieces to judge changes made to it."""

import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from forja.core.events import EventLog
from forja.core.gates import CheckSettings, InconclusivePolicy, Mode
from forja.core.process import ProcessIdentity
from forja.core.states import ExecutionState, Level
from forja.languages.python import PythonAdapter
from forja.orchestrator.measurer import PipelineMeasurer
from forja.orchestrator.ports import AttemptContext, TaskInfo
from tests.core.events.support import FakeClock
from tests.core.idempotency.conftest import Repo

FAKE_GITLEAKS = Path(__file__).with_name("fake_gitleaks.py")
FAKE_TOOLS = str(Path(__file__).with_name("fake_tools.py"))
LIZARD = (sys.executable, "-m", "lizard")
BLOCKING = CheckSettings(Mode.BLOCKING, InconclusivePolicy.BLOCK)
PREMISE = CheckSettings(Mode.BLOCKING, InconclusivePolicy.PREMISE)
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


class Run:
    """One process the pipeline started, as the runner announced it."""

    def __init__(
        self, where: tuple[Level, str, str], operation_id: str, details: Mapping[str, object]
    ) -> None:
        self.where = where
        self.operation_id = operation_id
        self.command: tuple[str, ...] = tuple(details["command"])  # type: ignore[call-overload]
        self.cwd = Path(str(details["cwd"]))
        self.timeout = details["timeout"]
        self.stdin_file = details["stdin_file"]
        self.env_names = tuple(details["env_names"])  # type: ignore[call-overload]

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
    ) -> PipelineMeasurer:
        standard = {
            name: BLOCKING for name in ("scope", "secrets", "format", "lint", "build", "tests")
        } | {"complexity": PREMISE}
        return PipelineMeasurer(
            adapter=self.adapter,
            git=self.repo.git,
            log=self.log,
            workdir=workdir or self.work / "run",
            host_env=self.repo.env,
            settings=settings or standard,
            values=values,
            lizard=self.lizard,
            gitleaks=gitleaks or (sys.executable, str(FAKE_GITLEAKS)),
            timeouts=timeouts,
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
