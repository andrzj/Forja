"""A run against real git: what it leaves in the repository, which the double cannot vouch for."""

from pathlib import Path

import pytest

from forja.core.events import EventLog
from forja.core.states import AttemptState, Level, TaskState
from forja.orchestrator.config import Budget
from forja.orchestrator.workspace_git import GitWorkspace
from tests.core.idempotency.conftest import Repo
from tests.orchestrator.fakes import (
    PASSED,
    REJECTED,
    ScriptedAgent,
    ScriptedMeasurer,
    ScriptedPlanner,
)
from tests.orchestrator.harness import TWO_TASKS, World

pytestmark = pytest.mark.integration


@pytest.fixture
def world(tmp_path: Path, repo: Repo, workspace: GitWorkspace) -> World:
    return World(tmp_path, repo, workspace)


def task_state(log: EventLog, task: str) -> TaskState:
    state = log.state.state_of(Level.TASK, task)
    assert isinstance(state, TaskState)
    return state


def branch_log(repo: Repo, branch: str) -> list[str]:
    return repo.sh("log", "--format=%s", branch).splitlines()


def test_what_the_run_leaves_in_git_is_one_branch_with_one_merge_per_task(world: World) -> None:
    world.run(planner=ScriptedPlanner(TWO_TASKS))

    run_branch = world.workspace.run_branch
    subjects = branch_log(world.repo, run_branch)
    assert subjects[0] == "merge: reduce the complexity of g"
    assert "merge: reduce the complexity of f" in subjects
    assert subjects.count("refactor: reduce the complexity of f") == 1
    assert "style: normalize formatting" in subjects
    assert world.repo.sh("branch", "--show-current") == "main"  # the user's branch is untouched
    assert (world.repo.path / "src").exists() is False
    assert not world.workspace.run_worktree.exists()
    assert len(world.repo.sh("worktree", "list").splitlines()) == 1  # only the repository


def test_the_run_branch_holds_the_agents_work_and_the_formatters(world: World) -> None:
    world.run()

    content = world.repo.sh("show", f"{world.workspace.run_branch}:src/t1.py")
    assert content == "def f():\n    return 1"
    assert world.repo.sh("show", f"{world.workspace.run_branch}:base.txt") == "formatted"


def test_the_commit_of_a_task_carries_the_agents_reason_and_the_runs_facts(world: World) -> None:
    world.run()

    commit = f"{world.workspace.run_branch}^2"
    assert world.repo.sh("log", "-1", "--format=%b", commit).startswith(
        "Split the long function in two."
    )
    trailers = world.repo.sh("log", "-1", "--format=%(trailers:only,unfold)", commit)
    assert "Agent: fake-cli 1.0" in trailers
    assert "Policy-Version: 0.0.0+abc" in trailers
    assert "Task-Id: t1" in trailers and "Stage-Id: t1-s" in trailers


def test_an_agent_that_touches_git_has_its_attempt_rejected(world: World) -> None:
    repo = world.repo
    agent = ScriptedAgent(meddle=lambda: repo.sh("branch", "sneaky"))

    _, log = world.run(agent=agent, budget=Budget(attempts_per_task=1))

    payload = log.state.transition_payload(Level.ATTEMPT, "t1-a1", AttemptState.REJECTED)
    assert payload is not None
    assert str(payload["reason"]).startswith("git changed while the agent ran: ")
    assert "sneaky" in str(payload["reason"])


def test_a_task_that_breaks_the_integration_gate_is_rolled_back_and_blocked(world: World) -> None:
    measurer = ScriptedMeasurer(integration_verdicts=(REJECTED, PASSED))
    before = world.repo.sh("rev-parse", "HEAD")

    _, log = world.run(measurer=measurer, planner=ScriptedPlanner(TWO_TASKS))

    assert task_state(log, "t1") is TaskState.BLOCKED
    assert task_state(log, "t2") is TaskState.INTEGRATED
    blocked = log.state.transition_payload(Level.TASK, "t1", TaskState.BLOCKED)
    assert blocked is not None and blocked["reason"] == "integration_gate"
    assert str(blocked["detail"]).startswith("gate 8 (complexity)")
    subjects = branch_log(world.repo, world.workspace.run_branch)
    assert "merge: reduce the complexity of f" not in subjects
    assert "merge: reduce the complexity of g" in subjects
    assert world.repo.sh("rev-parse", "HEAD") == before
