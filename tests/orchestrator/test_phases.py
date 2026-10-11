"""The whole orchestrator against real git and real processes, with only the judgment scripted."""

import asyncio
from pathlib import Path

import pytest

from forja.core.adapters.executor import ErrorKind
from forja.core.events import EventLog
from forja.core.states import AttemptState, ExecutionState, Level, StageState, TaskState
from forja.orchestrator.budget import Meter, read_consumption
from forja.orchestrator.config import Budget
from forja.orchestrator.outcome import ExitCode
from forja.orchestrator.phases import SUMMARY_NAME, Orchestrator, confirm_run
from forja.orchestrator.workspace_git import GitWorkspace
from tests.core.idempotency.conftest import Repo
from tests.orchestrator.fakes import (
    INCONCLUSIVE,
    PASSED,
    PASSED_WITH_A_GAP,
    REJECTED,
    ScriptedAgent,
    ScriptedMeasurer,
    ScriptedPlanner,
)
from tests.orchestrator.harness import ISOLATION, RUN, TWO_TASKS, World


@pytest.fixture
def world(tmp_path: Path, repo: Repo, workspace: GitWorkspace) -> World:
    return World(tmp_path, repo, workspace)


def task_state(log: EventLog, task: str) -> TaskState:
    state = log.state.state_of(Level.TASK, task)
    assert isinstance(state, TaskState)
    return state


def attempts(log: EventLog, task: str) -> dict[str, AttemptState]:
    found: dict[str, AttemptState] = {}
    for attempt in log.state.children_of(Level.ATTEMPT, f"{task}-s"):
        current = log.state.state_of(Level.ATTEMPT, attempt)
        assert isinstance(current, AttemptState)
        found[attempt] = current
    return found


def branch_log(repo: Repo, branch: str) -> list[str]:
    return repo.sh("log", "--format=%s", branch).splitlines()


# -- the happy path ----------------------------------------------------------------------------


def test_a_run_goes_from_the_confirmation_to_a_delivered_branch(world: World) -> None:
    measurer = ScriptedMeasurer(verdicts=(REJECTED, PASSED, PASSED))
    agent = ScriptedAgent()

    outcome, log = world.run(measurer=measurer, agent=agent, planner=ScriptedPlanner(TWO_TASKS))

    assert (outcome.state, outcome.exit_code) == (ExecutionState.DELIVERED, ExitCode.DELIVERED)
    assert [task_state(log, t) for t in ("t1", "t2")] == [TaskState.INTEGRATED] * 2
    assert attempts(log, "t1") == {"t1-a1": AttemptState.REJECTED, "t1-a2": AttemptState.COMMITTED}
    assert attempts(log, "t2") == {"t2-a1": AttemptState.COMMITTED}
    assert log.state.open_operations == {}
    assert str(world.run_dir / SUMMARY_NAME) in outcome.message


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


def test_the_summary_is_written_in_portuguese_and_names_the_branch(world: World) -> None:
    measurer = ScriptedMeasurer(metrics={"complexidade": 12.0})
    world.run(measurer=measurer)

    text = (world.run_dir / SUMMARY_NAME).read_text(encoding="utf-8")
    assert text.startswith(f"# Resumo da execução {RUN}")
    assert f"`{world.workspace.run_branch}`" in text
    assert "## Premissas assumidas\n\nNenhuma." in text
    assert "| complexidade | 12 | 12 |" in text
    assert f"git push -u <remoto> {world.workspace.run_branch}" in text


def test_the_summary_artifact_is_stored_and_cited_by_the_delivery(world: World) -> None:
    _, log = world.run()

    assert (world.run_dir / "store" / "artifacts" / "summary.json").exists()
    delivered = log.state.transition_payload(Level.EXECUTION, RUN, ExecutionState.DELIVERED)
    assert delivered == {"summary": str(world.run_dir / SUMMARY_NAME)}


def test_every_session_is_marked_in_the_log(world: World) -> None:
    _, log = world.run()

    consumption = read_consumption(log.path)
    assert consumption.seconds >= 0
    assert b"session_started" in log.path.read_bytes()
    assert b'"reason":"delivered"' in log.path.read_bytes()


# -- the baseline and the plan -----------------------------------------------------------------


def test_a_baseline_that_is_not_green_fails_the_run_before_any_task(world: World) -> None:
    outcome, log = world.run(measurer=ScriptedMeasurer(baseline_ok=False))

    assert (outcome.state, outcome.exit_code) == (ExecutionState.FAILED, ExitCode.FAILED)
    assert outcome.message == "baseline_not_green"
    assert log.state.children_of(Level.TASK, RUN) == []
    payload = log.state.transition_payload(Level.EXECUTION, RUN, ExecutionState.FAILED)
    assert payload == {"reason": "baseline_not_green", "problems": ["tests fail on the base"]}


def test_a_plan_with_nothing_to_do_still_ends_in_a_delivery(world: World) -> None:
    outcome, log = world.run(planner=ScriptedPlanner(()))

    assert outcome.state is ExecutionState.DELIVERED
    assert log.state.children_of(Level.TASK, RUN) == []


def test_the_plan_is_cut_to_the_number_of_tasks_the_budget_allows(world: World) -> None:
    _, log = world.run(planner=ScriptedPlanner(TWO_TASKS), budget=Budget(tasks=1))

    assert log.state.children_of(Level.TASK, RUN) == ["t1"]


def test_a_task_keeps_what_the_planner_said_about_it(world: World) -> None:
    _, log = world.run()

    payload = log.state.transition_payload(Level.TASK, "t1", TaskState.PENDING)
    assert payload == {
        "intent": "reduce the complexity of f",
        "scope": ["src/a.py"],
        "max_files": 8,
        "max_lines": 400,
    }


# -- rejection and blocking --------------------------------------------------------------------


def test_the_next_attempt_is_told_why_the_last_one_was_rejected(world: World) -> None:
    agent = ScriptedAgent()

    world.run(measurer=ScriptedMeasurer(verdicts=(REJECTED, PASSED)), agent=agent)

    first, second = agent.seen
    assert first.previous_rejection is None
    assert second.previous_rejection == ("gate 8 (complexity): too complex [src/a.py::f]")


def test_a_task_that_runs_out_of_attempts_is_blocked_and_the_run_goes_on(world: World) -> None:
    measurer = ScriptedMeasurer(verdicts=(REJECTED, REJECTED, PASSED))

    outcome, log = world.run(
        measurer=measurer, planner=ScriptedPlanner(TWO_TASKS), budget=Budget(attempts_per_task=2)
    )

    assert outcome.state is ExecutionState.DELIVERED
    assert task_state(log, "t1") is TaskState.BLOCKED
    assert task_state(log, "t2") is TaskState.INTEGRATED
    assert log.state.state_of(Level.STAGE, "t1-s") is StageState.EXHAUSTED
    blocked = log.state.transition_payload(Level.TASK, "t1", TaskState.BLOCKED)
    assert blocked == {"reason": "attempts_exhausted"}
    text = (world.run_dir / SUMMARY_NAME).read_text(encoding="utf-8")
    assert "- `t1` (reduce the complexity of f): attempts_exhausted" in text
    assert "tentativa `t1-a1` rejeitada: gate 8 (complexity): too complex" in text
    assert "- `t2`: reduce the complexity of g (1 tentativa(s), 0 rejeitada(s))" in text


def test_an_inconclusive_gate_that_blocks_discards_the_attempt_without_counting_it(
    world: World,
) -> None:
    _, log = world.run(measurer=ScriptedMeasurer(verdicts=(INCONCLUSIVE,)))

    assert task_state(log, "t1") is TaskState.BLOCKED
    discarded = log.state.transition_payload(Level.ATTEMPT, "t1-a1", AttemptState.DISCARDED)
    assert discarded is not None
    assert discarded["reason"] == "inconclusive_gate" and discarded["infra_failure"] is False
    assert str(discarded["detail"]).startswith("gate 8 (complexity): inconclusive (tool_failed)")
    assert log.state.transition_payload(Level.TASK, "t1", TaskState.BLOCKED) == {
        "reason": "inconclusive_gate"
    }


def test_a_gap_the_policy_lets_through_becomes_a_premise_in_the_summary(world: World) -> None:
    _, log = world.run(measurer=ScriptedMeasurer(verdicts=(PASSED_WITH_A_GAP,)))

    assert task_state(log, "t1") is TaskState.INTEGRATED
    text = (world.run_dir / SUMMARY_NAME).read_text(encoding="utf-8")
    assert "- complexity: não foi possível medir; a tarefa `t1` seguiu (tentativa `t1-a1`)." in text


def test_work_that_cannot_even_be_judged_is_rejected_with_the_reason(world: World) -> None:
    agent = ScriptedAgent(reject_diff="symlink may point outside the working copy")

    _, log = world.run(agent=agent, budget=Budget(attempts_per_task=1))

    payload = log.state.transition_payload(Level.ATTEMPT, "t1-a1", AttemptState.REJECTED)
    assert payload == {"reason": "symlink may point outside the working copy"}
    assert task_state(log, "t1") is TaskState.BLOCKED


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


# -- infrastructure ----------------------------------------------------------------------------


def test_a_transient_failure_waits_and_the_attempt_does_not_count(world: World) -> None:
    agent = ScriptedAgent(errors={0: ErrorKind.TRANSIENT, 1: ErrorKind.TRANSIENT})

    outcome, log = world.run(agent=agent)

    assert outcome.state is ExecutionState.DELIVERED
    assert world.slept == [30.0, 60.0]
    states = attempts(log, "t1")
    assert list(states.values()) == [
        AttemptState.DISCARDED,
        AttemptState.DISCARDED,
        AttemptState.COMMITTED,
    ]
    discard = log.state.transition_payload(Level.ATTEMPT, "t1-a1", AttemptState.DISCARDED)
    assert discard == {
        "reason": "transient",
        "detail": "the service said no",
        "infra_failure": True,
    }


def test_the_wait_grows_with_the_failures_in_a_row_up_to_the_last_step(world: World) -> None:
    agent = ScriptedAgent(errors={n: ErrorKind.TRANSIENT for n in range(4)})

    world.run(agent=agent, budget=Budget(infra_failures=9))

    assert world.slept == [30.0, 60.0, 120.0, 120.0]


def test_too_many_failures_in_a_row_pause_the_run_and_a_later_run_finishes_it(
    world: World,
) -> None:
    agent = ScriptedAgent(errors={n: ErrorKind.TRANSIENT for n in range(3)})

    outcome, log = world.run(agent=agent)

    assert (outcome.state, outcome.exit_code) == (ExecutionState.PAUSED, ExitCode.PAUSED)
    assert outcome.message == "3 infrastructure failures in a row on t1"
    assert log.state.state_of(Level.STAGE, "t1-s") is StageState.INFRA_PAUSED
    assert world.slept == [30.0, 60.0]
    log.close()

    resumed, log = world.run(agent=ScriptedAgent(), log=world.open())

    assert resumed.state is ExecutionState.DELIVERED
    assert task_state(log, "t1") is TaskState.INTEGRATED
    assert log.state.open_operations == {}


def test_a_blocking_error_pauses_the_run_at_once(world: World) -> None:
    agent = ScriptedAgent(errors={0: ErrorKind.BLOCKING})

    outcome, log = world.run(agent=agent)

    assert (outcome.state, outcome.exit_code) == (ExecutionState.PAUSED, ExitCode.PAUSED)
    assert outcome.message == "the agent cannot continue: the service said no"
    assert world.slept == []
    payload = log.state.transition_payload(Level.EXECUTION, RUN, ExecutionState.PAUSED)
    assert payload == {"reason": "the agent cannot continue: the service said no"}


def test_a_persistent_failure_waits_for_the_network_and_goes_on(world: World) -> None:
    world.network = [False, False, True]
    agent = ScriptedAgent(errors={0: ErrorKind.PERSISTENT})

    outcome, log = world.run(agent=agent)

    assert outcome.state is ExecutionState.DELIVERED
    assert world.slept == [60.0, 60.0, 60.0]
    assert b"waiting_for_network" in log.path.read_bytes()


def test_a_network_that_never_comes_back_pauses_the_run_when_the_budget_is_gone(
    world: World,
) -> None:
    world.network = [False]
    agent = ScriptedAgent(errors={0: ErrorKind.PERSISTENT})
    times = iter([0.0, 0.0, 0.0, 0.0, 10_000.0] + [10_000.0] * 50)

    log = world.open()
    confirm_run(log, world.config, ISOLATION)
    ctx = world.context(
        log, measurer=ScriptedMeasurer(), agent=agent, planner=ScriptedPlanner(), seconds_left=100.0
    )
    ctx.meter = Meter(100.0, read_consumption(log.path), clock=lambda: next(times))

    outcome = asyncio.run(Orchestrator(ctx).run())

    assert outcome.state is ExecutionState.PAUSED
    assert outcome.message == "the network did not come back before the budget ran out"


# -- time ---------------------------------------------------------------------------------------


def test_when_the_time_is_up_the_tasks_not_started_stay_pending_and_the_run_is_delivered(
    world: World,
) -> None:
    outcome, log = world.run(planner=ScriptedPlanner(TWO_TASKS), seconds_left=0.0)

    assert outcome.state is ExecutionState.DELIVERED
    assert [task_state(log, t) for t in ("t1", "t2")] == [TaskState.PENDING] * 2
    text = (world.run_dir / SUMMARY_NAME).read_text(encoding="utf-8")
    assert "Nenhuma." in text


# -- resuming ---------------------------------------------------------------------------------


def test_running_a_delivered_run_again_changes_nothing(world: World) -> None:
    first, log = world.run()
    size = log.path.stat().st_size
    log.close()

    again, log = world.run(log=world.open())

    assert again.state is first.state is ExecutionState.DELIVERED
    assert log.state.open_operations == {}
    assert b"session_started" in log.path.read_bytes()
    assert log.path.stat().st_size > size  # only the two session markers were added


def test_a_run_that_failed_goes_back_to_where_it_failed_when_run_again(world: World) -> None:
    failed, log = world.run(measurer=ScriptedMeasurer(baseline_ok=False))
    log.close()

    outcome, log = world.run(measurer=ScriptedMeasurer(baseline_ok=True), log=world.open())

    assert failed.state is ExecutionState.FAILED
    assert outcome.state is ExecutionState.DELIVERED
    assert task_state(log, "t1") is TaskState.INTEGRATED


def test_the_confirmation_is_recorded_as_the_first_two_states(world: World) -> None:
    log = world.open()

    confirm_run(log, world.config, ISOLATION)

    assert log.state.state_of(Level.EXECUTION, RUN) is ExecutionState.CONFIRMED
    assert log.state.transition_payload(Level.EXECUTION, RUN, ExecutionState.PREPARING) == {}


def test_a_call_that_ended_but_whose_result_was_lost_is_not_judged_as_if_it_were_clean(
    world: World,
) -> None:
    dying = ScriptedAgent(die_after_the_call=True)
    with pytest.raises(RuntimeError, match="died"):
        world.run(agent=dying)

    outcome, log = world.run(agent=ScriptedAgent(), log=world.open())

    assert outcome.state is ExecutionState.DELIVERED
    assert attempts(log, "t1") == {
        "t1-a1": AttemptState.DISCARDED,
        "t1-a2": AttemptState.COMMITTED,
    }
    lost = log.state.transition_payload(Level.ATTEMPT, "t1-a1", AttemptState.DISCARDED)
    assert lost == {"reason": "result_lost", "infra_failure": True}


def test_results_lost_again_and_again_pause_the_run_like_any_infrastructure_failure(
    world: World,
) -> None:
    for _ in range(3):
        with pytest.raises(RuntimeError):
            world.run(agent=ScriptedAgent(die_after_the_call=True), log=world.open())

    outcome, log = world.run(agent=ScriptedAgent(), log=world.open())

    assert (outcome.state, outcome.exit_code) == (ExecutionState.PAUSED, ExitCode.PAUSED)
    assert outcome.message == "3 infrastructure failures in a row on t1"
