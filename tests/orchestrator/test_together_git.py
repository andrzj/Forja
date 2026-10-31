"""Tasks that run at once against real git: the merges, the rollback and the guard on git."""

from pathlib import Path

import pytest

from forja.core.adapters.executor import ErrorKind
from forja.core.events import EventLog
from forja.core.states import ExecutionState, Level, TaskState
from forja.orchestrator.config import RunConfig
from forja.orchestrator.workspace_git import GitWorkspace
from tests.core.idempotency.conftest import Repo
from tests.orchestrator.fakes import PASSED, REJECTED, ScriptedMeasurer, ScriptedPlanner
from tests.orchestrator.harness import World
from tests.orchestrator.test_together import APART, Watched

pytestmark = pytest.mark.integration


@pytest.fixture
def world(tmp_path: Path, repo: Repo, workspace: GitWorkspace) -> World:
    return World(tmp_path, repo, workspace)


def together(world: World, agent: Watched, measurer: ScriptedMeasurer | None = None) -> tuple:  # type: ignore[type-arg]
    config: RunConfig = world.config.model_copy(update={"parallel_tasks": 2})
    return world.run(agent=agent, measurer=measurer, planner=ScriptedPlanner(APART), config=config)


def task_state(log: EventLog, task: str) -> object:
    return log.state.state_of(Level.TASK, task)


def merges(world: World) -> list[str]:
    subjects = world.repo.sh("log", "--format=%s", world.workspace.run_branch).splitlines()
    return [s for s in subjects if s.startswith("merge: ")]


def test_two_tasks_run_at_once_and_the_guard_on_git_sees_no_one_elses_work(world: World) -> None:
    agent = Watched(meet=2)  # each call waits for the other, with the other's branch already made

    outcome, log = together(world, agent)

    assert outcome.state is ExecutionState.DELIVERED
    assert agent.most == 2
    assert [task_state(log, t) for t in ("t1", "t2")] == [TaskState.INTEGRATED] * 2
    assert sorted(merges(world)) == ["merge: work on a", "merge: work on b"]
    run_branch = world.workspace.run_branch
    assert world.repo.sh("show", f"{run_branch}:src/t1.py").startswith("def f()")
    assert world.repo.sh("show", f"{run_branch}:src/t2.py").startswith("def f()")
    assert world.repo.sh("branch", "--show-current") == "main"
    assert len(world.repo.sh("worktree", "list").splitlines()) == 1


def test_the_merge_that_the_gate_rejects_leaves_the_one_before_it_in_the_run_branch(
    world: World,
) -> None:
    measurer = ScriptedMeasurer(integration_verdicts=(PASSED, REJECTED))

    outcome, log = together(world, Watched(meet=2), measurer)

    assert outcome.state is ExecutionState.DELIVERED
    states = {task_state(log, t) for t in ("t1", "t2")}
    assert states == {TaskState.INTEGRATED, TaskState.BLOCKED}
    (kept,) = merges(world)
    integrated = "t1" if task_state(log, "t1") is TaskState.INTEGRATED else "t2"
    assert kept == {"t1": "merge: work on a", "t2": "merge: work on b"}[integrated]
    blocked = "t2" if integrated == "t1" else "t1"
    run_branch = world.workspace.run_branch
    assert world.repo.sh("show", f"{run_branch}:src/{integrated}.py").startswith("def f()")
    assert world.repo.sh("ls-tree", "-r", "--name-only", run_branch).count(f"src/{blocked}.py") == 0


def test_the_merge_before_a_rejected_one_is_not_taken_with_it(world: World) -> None:
    measurer = ScriptedMeasurer(integration_verdicts=(REJECTED, PASSED))

    _, log = together(world, Watched(meet=2), measurer)

    assert {task_state(log, t) for t in ("t1", "t2")} == {TaskState.INTEGRATED, TaskState.BLOCKED}
    assert len(merges(world)) == 1


def test_a_task_that_stops_the_run_leaves_no_half_merge_and_the_user_branch_alone(
    world: World,
) -> None:
    before = world.repo.sh("rev-parse", "HEAD")
    agent = Watched(meet=2)
    agent.errors = {0: ErrorKind.BLOCKING}

    outcome, log = together(world, agent)

    assert outcome.state is ExecutionState.PAUSED
    assert agent.inside == 0
    integrated = sum(task_state(log, t) is TaskState.INTEGRATED for t in ("t1", "t2"))
    assert len(merges(world)) == integrated  # a merge in the branch is a task the log integrated
    assert world.repo.sh("rev-parse", "HEAD") == before
    assert world.repo.sh("branch", "--show-current") == "main"
    assert world.repo.sh("status", "--porcelain") == ""
