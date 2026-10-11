"""The real parts of a run, assembled from a ``RunConfig``: git, tools, agent, planner, meter.

A new run and a resumed one go through the same door, because everything the run needs is in its
``RunConfig`` (kept in the log when the person confirmed it). Nothing here decides anything about
the work; this only connects the pieces the orchestrator is written against.
"""

import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from forja.checks.specs import default_registry
from forja.core.adapters.executor import RolePermissions, locate_in_path
from forja.core.authorization import ProtectedBranches
from forja.core.confirmation import Confirmation
from forja.core.events import EventLog, LogEventSink
from forja.core.gates import CheckSettings
from forja.core.gitguard import GuardedGit
from forja.core.idempotency.git import Git
from forja.core.ids import new_id
from forja.core.isolation import IsolationLevel, IsolationRecord
from forja.core.locking import LockOwner, LockPolicy, acquire_repository_lock, repository_id
from forja.core.locking.repository import HeldLock
from forja.core.paths import forja_home, locks_dir, run_dir
from forja.core.states import Level
from forja.executors import ClaudeCodeAdapter
from forja.languages.python import PythonAdapter
from forja.orchestrator.agent_runner import ExecutorAgentRunner
from forja.orchestrator.budget import Meter
from forja.orchestrator.config import RunConfig, load_config
from forja.orchestrator.measurer import PipelineMeasurer
from forja.orchestrator.operations import Journal
from forja.orchestrator.phases import confirm_run
from forja.orchestrator.planner import ComplexityPlanner
from forja.orchestrator.ports import RunContext
from forja.orchestrator.workspace_git import (
    GitWorkspace,
    Layout,
    detect_identity,
    git_environment,
)
from forja.ui.view import ViewModel

GIT_ENVIRONMENT = (
    "PATH", "HOME", "USERPROFILE", "SYSTEMROOT", "TEMP", "TMP", "APPDATA", "LOCALAPPDATA",
    "LANG", "LC_ALL", "PATHEXT", "COMSPEC",
)  # fmt: skip
NETWORK_PROBES_WITHOUT_A_PERSON = 60
FORJA_VERSION = "0.0.0"
POLICY_VERSION = "0.0.0+default"
REDUCED = Confirmation(
    IsolationRecord(agent=IsolationLevel.REDUCED, repo_code=IsolationLevel.REDUCED)
)


def git_base_environment(environ: Mapping[str, str]) -> dict[str, str]:
    wanted = {name.upper() for name in GIT_ENVIRONMENT}
    return {name: value for name, value in environ.items() if name.upper() in wanted}


def repo_python(repo: Path) -> tuple[str, ...]:
    """The interpreter of the repository itself, which has what its tests import."""
    for relative in (".venv/Scripts/python.exe", ".venv/bin/python", "venv/Scripts/python.exe",
                     "venv/bin/python"):  # fmt: skip
        if (repo / relative).is_file():
            return (str(repo / relative),)
    found = locate_in_path("python") or locate_in_path("python3")
    return (str(found) if found else sys.executable,)


def standard_settings() -> dict[str, CheckSettings]:
    """The mode and the policy for inconclusive of every check, from the defaults of the spec."""
    return {spec.id: spec.default_settings for spec in default_registry()}


def in_scope(path: str, scope: tuple[str, ...]) -> bool:
    """Whether a file is under one of the paths the person asked for (all, when none)."""
    if not scope:
        return True
    return any(
        path == item.rstrip("/") or path.startswith(item.rstrip("/") + "/") for item in scope
    )


def missing_tool(name: str) -> str:
    """Where a tool is, or an absolute path that is not there: a bare name could be run from the
    current directory, which belongs to the repository and not to the person."""
    found = locate_in_path(name)
    return str(found) if found else str(Path(sys.prefix) / f"{name}-is-not-installed")


def git_executable() -> str:
    found = locate_in_path("git")
    if found is None:
        raise FileNotFoundError("git is not installed or not on the PATH; run `forja doctor`")
    return str(found)


@dataclass
class Session:
    run_id: str
    log: EventLog
    context: RunContext
    view: ViewModel
    lock: HeldLock
    directory: Path
    resumed: bool

    def close(self) -> None:
        self.lock.release()
        self.log.close()


def new_config(
    *,
    repo: Path,
    base_commit: str,
    executor_name: str,
    executor_path: Path,
    executor_version: str,
    tokens: int,
    scope: tuple[str, ...] = (),
) -> RunConfig:
    from forja.orchestrator.config import Budget, ExecutorRef, Objective  # noqa: PLC0415

    return RunConfig(
        repo=str(repo),
        base_commit=base_commit,
        objective=Objective.REFACTOR,
        implementer=ExecutorRef(
            name=executor_name, path=str(executor_path), version=executor_version
        ),
        budget=Budget(tokens=tokens),
        forja_version=FORJA_VERSION,
        policy_version=POLICY_VERSION,
        scope=scope,
    )


async def open_session(
    config: RunConfig | None,
    *,
    run_id: str | None = None,
    environ: Mapping[str, str] | None = None,
    interactive: bool = True,
    isolation: Confirmation = REDUCED,
    home: Path | None = None,
) -> Session:
    """Take the repository's lock and build everything a run needs.

    With a ``run_id`` of an existing run the config comes from its log (a resume); without one
    a new run is created and ``config`` is what the person confirmed.
    """
    env = os.environ if environ is None else environ
    resumed = run_id is not None
    run_id = run_id or new_id()
    base = home or forja_home(environ=env)
    directory = base / "runs" / run_id if home else run_dir(run_id, environ=env)
    directory.mkdir(parents=True, exist_ok=True)
    log = EventLog.open(directory / "events.jsonl", run_id)
    if resumed:
        config = load_config(log.state)
    if config is None:
        raise ValueError("a new run needs the configuration the person confirmed")
    repo = Path(config.repo)
    plain = Git(
        repo, executable=git_executable(), env=git_base_environment(env), timeout=60,
        log_dir=directory / "logs" / "git",
    )  # fmt: skip
    lock = await acquire_repository_lock(
        (base / "locks" / await repository_id(plain))
        if home
        else locks_dir(await repository_id(plain), environ=env),
        LockOwner.current(run_id),
        LockPolicy.refuse(),
    )
    try:
        if not resumed:
            confirm_run(log, config, isolation)
        context = await _context(config, log, directory, base, env, plain, run_id, interactive)
    except BaseException:
        lock.release()
        log.close()
        raise
    view = ViewModel(
        objective="refatorar",
        repo=repo.name,
        branch=f"forja-run/{run_id}",
        isolation="isolamento reduzido",
        token_limit=config.budget.tokens,
        attempts_max=config.budget.attempts_per_task,
    )
    view.replay(log.path)
    log.subscribe(view.apply)
    return Session(run_id, log, context, view, lock, directory, resumed)


async def _context(
    config: RunConfig,
    log: EventLog,
    directory: Path,
    base: Path,
    env: Mapping[str, str],
    plain: Git,
    run_id: str,
    interactive: bool,
) -> RunContext:
    repo = Path(config.repo)
    identity = await detect_identity(plain, config.implementer.name)
    branch = (await plain.lines("rev-parse", "--abbrev-ref", "HEAD"))[0]
    git = GuardedGit(
        repo,
        executable=git_executable(),
        env=git_environment(git_base_environment(env), identity),
        timeout=120,
        log_dir=directory / "logs" / "guard",
        protected=ProtectedBranches(frozenset({"main", "master", branch})),
    )
    workspace = GitWorkspace(git, run_id=run_id, layout=Layout.for_run(base, run_id))

    def sinks(level: Level, target: str, operation: str) -> LogEventSink:
        return LogEventSink(log, level, target, operation)

    measurer = PipelineMeasurer(
        adapter=PythonAdapter(python=repo_python(repo)),
        git=git,
        log=log,
        workdir=directory / "measure",
        host_env=env,
        settings=standard_settings(),
        lizard=(sys.executable, "-m", "lizard"),
        gitleaks=(missing_tool("gitleaks"),),
    )

    async def functions(worktree: Path) -> Mapping[tuple[str, str], int]:
        found = await measurer.functions(worktree, sinks)
        return {key: ccn for key, ccn in found.items() if in_scope(key[0], config.scope)}

    commands = ("forja agente",) if locate_in_path("forja") else ()
    agent = ExecutorAgentRunner(
        ClaudeCodeAdapter(),
        Path(config.implementer.path),
        {**env, "FORJA_AGENT_PYTHON": repo_python(repo)[0]},
        log,
        permissions=RolePermissions(can_edit_files=True, allowed_commands=commands),
    )
    return RunContext(
        journal=Journal(log),
        config=config,
        workspace=workspace,
        measurer=measurer,
        agent=agent,
        planner=ComplexityPlanner(functions),
        meter=Meter(config.budget.tokens, log.path, enforce=not interactive),
        run_dir=directory,
        max_network_probes=None if interactive else NETWORK_PROBES_WITHOUT_A_PERSON,
    )
