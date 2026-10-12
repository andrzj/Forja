"""One run assembled from real git and real processes, shared by the end-to-end tests."""

import asyncio
import os
import shutil
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from forja.core.authorization import ProtectedBranches
from forja.core.confirmation import Confirmation
from forja.core.events import EventLog
from forja.core.gitguard import GuardedGit
from forja.core.isolation import IsolationLevel, IsolationRecord
from forja.core.states import ExecutionState, Level
from forja.orchestrator.budget import Meter
from forja.orchestrator.config import Budget, ExecutorRef, Objective, RunConfig
from forja.orchestrator.operations import Hook, Journal
from forja.orchestrator.outcome import Outcome
from forja.orchestrator.phases import Orchestrator, confirm_run
from forja.orchestrator.ports import PlannedTask, RunContext
from forja.orchestrator.workspace_git import GitWorkspace, Identity, Layout, git_environment
from forja.testing import MemoryRepo, MemoryWorkspace
from tests.core.events.support import FakeClock
from tests.core.idempotency.conftest import Repo
from tests.orchestrator.fakes import ScriptedAgent, ScriptedMeasurer, ScriptedPlanner

RUN = "r1abcdef0123"
IDENTITY = Identity("Forja (fake-cli)", "forja@localhost", "Dev Person", "dev@example.com")
ISOLATION = Confirmation(
    IsolationRecord(agent=IsolationLevel.ENVIRONMENT, repo_code=IsolationLevel.ENVIRONMENT)
)
TWO_TASKS = (
    PlannedTask("reduce the complexity of f", ("src/a.py",), 8, 400),
    PlannedTask("reduce the complexity of g", ("src/b.py",), 8, 400),
)


def minimal_env(home: Path) -> dict[str, str]:
    env = {
        "PATH": os.environ["PATH"],
        "HOME": str(home),
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
    }
    if sys.platform == "win32":
        env["SYSTEMROOT"] = os.environ["SYSTEMROOT"]
    return env


def build_template(path: Path) -> None:
    """A repository with one commit on ``main``; copied for every run."""
    home = path.parent / "template-home"
    home.mkdir()
    path.mkdir()
    env = minimal_env(home)
    base = ["git", "-c", "user.name=forja", "-c", "user.email=forja@example.com"]
    (path / "base.txt").write_text("base\n", encoding="utf-8")
    for args in (
        ["init", "-b", "main"],
        ["config", "core.autocrlf", "false"],
        ["add", "base.txt"],
        ["commit", "-m", "base"],
    ):
        subprocess.run([*base, *args], cwd=path, env=env, check=True, capture_output=True)


def make_workspace(repo: Repo, root: Path) -> GitWorkspace:
    git = GuardedGit(
        repo.path,
        executable=shutil.which("git") or "git",
        env=git_environment(repo.env, IDENTITY),
        timeout=60,
        log_dir=root / "logs" / "guard",
        protected=ProtectedBranches(frozenset({"main"})),
    )
    return GitWorkspace(git, run_id=RUN, layout=Layout(root / "wt"), git_running=lambda: False)


class World:
    """One run being assembled: the pieces a test may want to look at afterwards."""

    def __init__(self, root: Path, repo: Repo, workspace: GitWorkspace) -> None:
        self.repo = repo
        self._assemble(root, workspace, str(repo.path), repo.sh("rev-parse", "HEAD"))

    def _assemble(self, root: Path, workspace: Any, repo_path: str, base_commit: str) -> None:
        self.root, self.workspace = root, workspace
        self.run_dir = root / "run"
        self.slept: list[float] = []
        self.network: list[bool] = [True]
        self.config = RunConfig(
            repo=repo_path,
            base_commit=base_commit,
            objective=Objective.REFACTOR,
            implementer=ExecutorRef(name="fake-cli", path="/bin/fake", version="1.0"),
            forja_version="0.0.0",
            policy_version="0.0.0+abc",
        )

    @classmethod
    def create(cls, root: Path, template: Path) -> "World":
        (root / "home").mkdir(parents=True)
        shutil.copytree(template, root / "repo")
        return cls.at(root)

    @classmethod
    def at(cls, root: Path) -> "World":
        repo = Repo(root / "repo", minimal_env(root / "home"), root / "logs")
        return cls(root, repo, make_workspace(repo, root))

    async def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)

    async def network_is_up(self) -> bool:
        return self.network.pop(0) if len(self.network) > 1 else self.network[0]

    def open(self, **log_options: Any) -> EventLog:
        log_options.setdefault("clock", FakeClock())
        return EventLog.open(self.run_dir / "events.jsonl", RUN, **log_options)

    def context(
        self,
        log: EventLog,
        *,
        measurer: ScriptedMeasurer,
        agent: ScriptedAgent,
        planner: ScriptedPlanner,
        budget: Budget | None = None,
        token_limit: int = 2_000_000,
        hook: Hook | None = None,
    ) -> RunContext:
        config = self.config.model_copy(update={"budget": budget or Budget()})
        journal = Journal(log, hook=hook) if hook is not None else Journal(log)
        return RunContext(
            journal=journal,
            config=config,
            workspace=self.workspace,
            measurer=measurer,
            agent=agent,
            planner=planner,
            meter=Meter(token_limit, log.path, enforce=True),
            run_dir=self.run_dir,
            sleep=self.sleep,
            network_is_up=self.network_is_up,
        )

    def run(
        self,
        *,
        measurer: Any = None,
        agent: ScriptedAgent | None = None,
        planner: ScriptedPlanner | None = None,
        budget: Budget | None = None,
        token_limit: int = 2_000_000,
        log: EventLog | None = None,
        hook: Hook | None = None,
    ) -> tuple[Outcome, EventLog]:
        opened = log or self.open()
        if not opened.state.has_target(Level.EXECUTION, RUN):
            config = self.config.model_copy(update={"budget": budget or Budget()})
            confirm_run(opened, config, ISOLATION)
        ctx = self.context(
            opened,
            measurer=measurer or ScriptedMeasurer(),
            agent=agent or ScriptedAgent(),
            planner=planner or ScriptedPlanner(),
            budget=budget,
            token_limit=token_limit,
            hook=hook,
        )
        return asyncio.run(Orchestrator(ctx).run()), opened


class MemoryWorld(World):
    """The same run with git in memory: no repository, no git process, no waiting for either.

    The behaviour of ``MemoryWorkspace`` is held to ``GitWorkspace``'s by a contract test, so what
    a run does here is what it does against git. Tests of git itself use ``World``.
    """

    def __init__(self, root: Path, files: Mapping[str, str] | None = None) -> None:
        self.memory = MemoryRepo(files or {"base.txt": "base"})
        workspace = MemoryWorkspace(self.memory, run_id=RUN, layout=Layout(root / "wt"))
        self._assemble(root, workspace, str(root / "repo"), self.memory.base)


def execution_state(log: EventLog) -> ExecutionState:
    state = log.state.state_of(Level.EXECUTION, RUN)
    assert isinstance(state, ExecutionState)
    return state
