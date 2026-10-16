"""The view follows the events of a run: tasks, attempts, gates, the feed and the tokens."""

from pathlib import Path

import pytest

from forja.core.states import AttemptState, ExecutionState, Level, TaskState
from forja.ui.view import GATES, GateStatus, ViewModel, blank_view
from tests.orchestrator.fakes import PASSED, REJECTED, ScriptedMeasurer, ScriptedPlanner
from tests.orchestrator.harness import TWO_TASKS, MemoryWorld
from tests.ui.support import activity, model, progress, tool, transition


def statuses(view_model: ViewModel) -> dict[str, GateStatus]:
    return dict(view_model.snapshot().gates)


def test_the_execution_state_and_its_reason_are_shown() -> None:
    view = model()
    view.apply(transition(Level.EXECUTION, "r1", "paused", payload={"reason": "interrupted"}))

    snapshot = view.snapshot()

    assert (snapshot.state, snapshot.message) == ("paused", "interrupted")
    assert snapshot.finished


def test_a_state_without_a_reason_clears_the_message() -> None:
    view = model()
    view.apply(transition(Level.EXECUTION, "r1", "paused", payload={"reason": "interrupted"}))
    view.apply(transition(Level.EXECUTION, "r1", "executing"))

    assert view.snapshot().message == ""
    assert not view.snapshot().finished


def test_tasks_are_counted_and_the_current_one_is_the_one_in_progress() -> None:
    view = model()
    for number in (1, 2, 3):
        payload = {"intent": f"reduce {number}"}
        view.apply(transition(Level.TASK, f"t{number}", TaskState.PENDING, payload=payload))
    view.apply(transition(Level.TASK, "t1", TaskState.IN_PROGRESS))
    view.apply(transition(Level.TASK, "t1", TaskState.INTEGRATED))
    view.apply(transition(Level.TASK, "t2", TaskState.IN_PROGRESS))

    snapshot = view.snapshot()

    assert (snapshot.tasks_total, snapshot.tasks_done) == (3, 1)
    assert (snapshot.task_id, snapshot.task_intent) == ("t2", "reduce 2")


def test_a_blocked_task_counts_as_done() -> None:
    view = model()
    view.apply(transition(Level.TASK, "t1", TaskState.PENDING, payload={"intent": "x"}))
    view.apply(transition(Level.TASK, "t1", TaskState.BLOCKED))

    assert view.snapshot().tasks_done == 1


def test_integrated_and_blocked_tasks_are_told_apart() -> None:
    view = model()
    for number, final in (
        (1, TaskState.INTEGRATED),
        (2, TaskState.BLOCKED),
        (3, TaskState.BLOCKED),
    ):
        view.apply(transition(Level.TASK, f"t{number}", TaskState.PENDING, payload={"intent": "x"}))
        view.apply(transition(Level.TASK, f"t{number}", final))

    snapshot = view.snapshot()

    assert (snapshot.tasks_done, snapshot.tasks_integrated, snapshot.tasks_blocked) == (3, 1, 2)


def test_a_new_attempt_has_its_number_and_clean_gates() -> None:
    view = model()
    view.apply(tool("intent", "run_tool:t1-a1:lint:1"))
    view.apply(transition(Level.ATTEMPT, "t1-a2", AttemptState.CREATED))

    assert view.snapshot().attempt == 2
    assert set(statuses(view).values()) == {GateStatus.PENDING}


def test_the_pipeline_is_in_order_so_what_came_before_a_running_gate_passed() -> None:
    view = model()

    view.apply(tool("intent", "run_tool:t1-a1:lint:1"))

    assert statuses(view) == {
        "scope": GateStatus.PASSED, "secrets": GateStatus.PASSED, "format": GateStatus.PASSED,
        "lint": GateStatus.RUNNING, "build": GateStatus.PENDING, "tests": GateStatus.PENDING,
        "complexity": GateStatus.PENDING, "mutation": GateStatus.PENDING,
        "crap": GateStatus.PENDING,
    }  # fmt: skip


def test_the_lint_of_the_parent_commit_is_the_lint_gate() -> None:
    view = model()
    view.apply(tool("intent", "run_tool:t1-a1:lint_before:1"))

    assert statuses(view)["lint"] is GateStatus.RUNNING


def test_what_is_not_a_tool_run_of_a_gate_changes_nothing() -> None:
    view = model()
    view.apply(tool("intent", "run_tool:r1:tests:1", operation="run_tool"))
    before = statuses(view)

    view.apply(tool("intent", "commit_stage:t1", operation="commit_stage"))
    view.apply(tool("effect", "run_tool:t1-a1:lint:1"))
    view.apply(tool("intent", "run_tool:t1-a1:unknown_check:1"))

    assert statuses(view) == before


def test_an_approved_attempt_passed_every_gate() -> None:
    view = model()
    view.apply(transition(Level.ATTEMPT, "t1-a1", AttemptState.APPROVED))

    assert set(statuses(view).values()) == {GateStatus.PASSED}


def test_a_rejection_marks_the_gate_that_stopped_it_and_is_kept_in_the_news() -> None:
    view = model()
    view.apply(tool("intent", "run_tool:t1-a1:build:1"))
    reason = "gate 5 (build): src/a.py does not compile"
    view.apply(
        transition(Level.ATTEMPT, "t1-a1", AttemptState.REJECTED, payload={"reason": reason})
    )

    snapshot = view.snapshot()

    assert dict(snapshot.gates)["build"] is GateStatus.FAILED
    assert dict(snapshot.gates)["tests"] is GateStatus.PENDING
    assert snapshot.rejections == (f"t1-a1: {reason}",)
    assert snapshot.rejections_total == 1


def test_a_discarded_attempt_is_in_the_news_with_its_reason() -> None:
    view = model()
    view.apply(
        transition(
            Level.ATTEMPT, "t1-a1", AttemptState.DISCARDED, payload={"reason": "interrupted"}
        )
    )

    assert view.snapshot().rejections == ("t1-a1: interrupted",)


def test_the_feed_says_what_the_agent_does_in_portuguese() -> None:
    view = model()
    view.apply(activity("file_read", path="src/a.py"))
    view.apply(activity("file_edit", path="src/a.py", added=14, removed=32))
    view.apply(activity("command", command="forja agente testar"))
    view.apply(activity("text", text="pronto"))
    view.apply(activity("error", message="falhou"))
    view.apply(progress("waiting_for_network"))

    feed = view.snapshot().feed

    assert [(line.kind, line.text) for line in feed] == [
        ("read", "leu src/a.py"),
        ("edit", "editou src/a.py (+14 -32)"),
        ("command", "rodou forja agente testar"),
        ("text", "pronto"),
        ("error", "falhou"),
        ("note", "aguardando a rede voltar"),
    ]
    assert feed[0].time == "12:31:07"


def test_the_feed_keeps_the_last_lines_and_counts_all_of_them() -> None:
    view = model()
    for number in range(100):
        view.apply(activity("text", text=str(number)))

    snapshot = view.snapshot()

    assert len(snapshot.feed) == 60
    assert snapshot.feed[-1].text == "99"
    assert snapshot.feed_total == 100


def test_tokens_add_up_and_the_fraction_follows_the_limit() -> None:
    view = model(token_limit=1000)
    view.apply(activity("usage", input=300, output=100))
    view.apply(activity("usage", input=50, output=0))
    view.apply(activity("usage", input="x", output=True))

    snapshot = view.snapshot()

    assert snapshot.tokens_used == 450
    assert snapshot.tokens_fraction == pytest.approx(0.45)


def test_no_limit_means_no_fraction() -> None:
    assert model(token_limit=0).snapshot().tokens_fraction == 0.0


def test_the_elapsed_time_is_the_earlier_sessions_plus_this_one() -> None:
    now = [100.0]
    view = model(clock=lambda: now[0], seconds_before=60.0)
    now[0] += 5

    assert view.snapshot().elapsed == 65.0


def test_a_blank_view_can_be_changed() -> None:
    assert blank_view(repo="x").repo == "x"


def test_a_whole_run_ends_with_every_task_done_and_what_was_rejected_on_the_way(
    tmp_path: Path,
) -> None:
    world = MemoryWorld(tmp_path)
    log = world.open()
    live = model()
    log.subscribe(live.apply)

    world.run(
        planner=ScriptedPlanner(TWO_TASKS),
        measurer=ScriptedMeasurer(verdicts=(REJECTED, PASSED)),
        log=log,
    )

    snapshot = live.snapshot()
    assert snapshot.state == ExecutionState.DELIVERED
    assert (snapshot.tasks_total, snapshot.tasks_done) == (2, 2)
    assert snapshot.rejections_total == 1
    assert "gate 8 (complexity)" in snapshot.rejections[0]
    assert dict(snapshot.gates) == dict.fromkeys(GATES, GateStatus.PASSED)


def test_a_view_rebuilt_from_the_log_is_the_view_that_followed_the_run(tmp_path: Path) -> None:
    world = MemoryWorld(tmp_path)
    log = world.open()
    followed = model()
    log.subscribe(followed.apply)
    world.run(measurer=ScriptedMeasurer(verdicts=(REJECTED, PASSED)), log=log)

    rebuilt = model()
    rebuilt.replay(log.path)

    one, other = followed.snapshot(), rebuilt.snapshot()
    assert (one.state, one.tasks_done, one.attempt) == (
        other.state,
        other.tasks_done,
        other.attempt,
    )
    assert one.rejections == other.rejections
    assert one.gates == other.gates


def test_replaying_a_log_that_does_not_exist_changes_nothing(tmp_path: Path) -> None:
    view = model()
    view.replay(tmp_path / "none.jsonl")

    assert view.snapshot().state == "preparing"


def test_replaying_stops_at_a_torn_last_line(tmp_path: Path) -> None:
    world = MemoryWorld(tmp_path)
    world.run()
    path = world.run_dir / "events.jsonl"
    path.write_bytes(path.read_bytes() + b'{"torn":')

    view = model()
    view.replay(path)

    assert view.snapshot().state == ExecutionState.DELIVERED
