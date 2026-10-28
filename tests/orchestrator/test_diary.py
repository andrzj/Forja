"""The log book of a task is read from the log: the same entries after a resume or a cut log."""

from pathlib import Path

import pytest
from pydantic import JsonValue

from forja.core.events import EventLog
from forja.core.events.log import read_state
from forja.core.states import (
    AttemptState,
    ExecutionState,
    Level,
    StageState,
    TaskState,
)
from forja.orchestrator.diary import (
    BLOCKED,
    DIARY_LIMIT,
    EXHAUSTED,
    HYPOTHESIS_REQUEST,
    LINE_CUT,
    SAID_CUT,
    Decision,
    Entry,
    Outcome,
    diary_text,
    hypothesis_request,
    stage_diary,
    stage_entries,
    stage_hypothesis,
    task_decisions,
    task_entries,
)
from forja.orchestrator.summary import DIARY_CUT, diary_lines
from tests.core.events.support import FakeClock
from tests.orchestrator.harness import RUN

S = AttemptState


@pytest.fixture
def log(tmp_path: Path) -> EventLog:
    opened = EventLog.open(tmp_path / "events.jsonl", RUN, clock=FakeClock())
    opened.append_transition(Level.EXECUTION, RUN, None, ExecutionState.PREPARING)
    opened.append_transition(Level.TASK, "t1", None, TaskState.PENDING, parent_id=RUN)
    opened.append_transition(Level.STAGE, "t1", None, StageState.PENDING, parent_id="t1")
    return opened


def attempt(
    log: EventLog,
    name: str,
    *,
    said: str | None = None,
    end: AttemptState | None = None,
    payload: dict[str, JsonValue] | None = None,
    stage: str = "t1",
) -> None:
    """Run an attempt through the states up to ``end`` (``None``: left where the agent ran)."""
    log.append_transition(Level.ATTEMPT, name, None, S.CREATED, parent_id=stage)
    log.append_transition(Level.ATTEMPT, name, S.CREATED, S.WORKCOPY_READY)
    log.append_transition(Level.ATTEMPT, name, S.WORKCOPY_READY, S.AGENT_RUNNING)
    if end is None:
        return
    if end is S.DISCARDED:
        log.append_transition(Level.ATTEMPT, name, S.AGENT_RUNNING, S.DISCARDED, payload=payload)
        return
    log.append_transition(
        Level.ATTEMPT, name, S.AGENT_RUNNING, S.VALIDATING, payload={"reason": said or ""}
    )
    log.append_transition(Level.ATTEMPT, name, S.VALIDATING, end, payload=payload)


def test_a_rejected_attempt_keeps_what_the_agent_said_and_why_it_was_rejected(
    log: EventLog,
) -> None:
    attempt(log, "t1-a1", said="renamed it", end=S.REJECTED, payload={"reason": "gate 4 (crap)"})

    assert task_entries(log.state, "t1") == [
        Entry("t1", "t1-a1", "renamed it", Outcome.REJECTED, "gate 4 (crap)")
    ]


def test_an_approved_attempt_lists_the_gates_it_passed(log: EventLog) -> None:
    attempt(log, "t1-a1", said="done", end=S.APPROVED, payload={"gates_passed": ["scope", "lint"]})

    assert stage_entries(log.state, "t1") == [
        Entry("t1", "t1-a1", "done", Outcome.APPROVED, "scope, lint")
    ]


def test_an_approval_without_a_list_of_gates_has_no_detail(log: EventLog) -> None:
    attempt(log, "t1-a1", said="done", end=S.APPROVED, payload={})

    assert stage_entries(log.state, "t1")[0].detail == ""


def test_an_attempt_discarded_for_infrastructure_says_so(log: EventLog) -> None:
    attempt(log, "t1-a1", end=S.DISCARDED, payload={"reason": "network", "infra_failure": True})
    attempt(
        log, "t1-a2", end=S.DISCARDED, payload={"reason": "interrupted", "infra_failure": False}
    )

    first, second = stage_entries(log.state, "t1")

    assert (first.outcome, first.detail, first.infrastructure) == (
        Outcome.DISCARDED,
        "network",
        True,
    )
    assert (second.outcome, second.infrastructure) == (Outcome.DISCARDED, False)
    assert first.said == ""


def test_an_attempt_that_has_not_ended_is_open(log: EventLog) -> None:
    attempt(log, "t1-a1")

    assert stage_entries(log.state, "t1") == [Entry("t1", "t1-a1", "", Outcome.OPEN)]


def test_an_attempt_still_validating_keeps_what_the_agent_said(log: EventLog) -> None:
    log.append_transition(Level.ATTEMPT, "t1-a1", None, S.CREATED, parent_id="t1")
    log.append_transition(Level.ATTEMPT, "t1-a1", S.CREATED, S.WORKCOPY_READY)
    log.append_transition(Level.ATTEMPT, "t1-a1", S.WORKCOPY_READY, S.AGENT_RUNNING)
    log.append_transition(
        Level.ATTEMPT, "t1-a1", S.AGENT_RUNNING, S.VALIDATING, payload={"reason": "half way"}
    )

    assert stage_entries(log.state, "t1") == [Entry("t1", "t1-a1", "half way", Outcome.OPEN)]


def test_the_entries_of_a_task_follow_its_stages_and_attempts_in_order(log: EventLog) -> None:
    log.append_transition(Level.STAGE, "t1-t", None, StageState.PENDING, parent_id="t1")
    attempt(log, "t1-a1", said="a", end=S.REJECTED, payload={"reason": "x"})
    attempt(log, "t1-a2", said="b", end=S.APPROVED, payload={"gates_passed": []})
    attempt(log, "t1-ta1", said="c", end=S.REJECTED, payload={"reason": "y"}, stage="t1-t")

    assert [(e.stage, e.attempt) for e in task_entries(log.state, "t1")] == [
        ("t1", "t1-a1"),
        ("t1", "t1-a2"),
        ("t1-t", "t1-ta1"),
    ]


def test_an_exhausted_stage_and_a_blocked_task_are_decisions_with_their_reason(
    log: EventLog,
) -> None:
    log.append_transition(Level.STAGE, "t1", StageState.PENDING, StageState.IN_PROGRESS)
    log.append_transition(
        Level.STAGE,
        "t1",
        StageState.IN_PROGRESS,
        StageState.EXHAUSTED,
        payload={"reason": "3 attempts"},
    )
    log.append_transition(Level.TASK, "t1", TaskState.PENDING, TaskState.IN_PROGRESS)
    log.append_transition(
        Level.TASK, "t1", TaskState.IN_PROGRESS, TaskState.BLOCKED, payload={"reason": "3 attempts"}
    )

    assert task_decisions(log.state, "t1") == [
        Decision("t1", EXHAUSTED, "3 attempts"),
        Decision("t1", BLOCKED, "3 attempts"),
    ]


def test_a_task_that_went_well_has_no_decision(log: EventLog) -> None:
    assert task_decisions(log.state, "t1") == []


def test_a_decision_without_a_reason_has_an_empty_one(log: EventLog) -> None:
    log.append_transition(Level.TASK, "t1", TaskState.PENDING, TaskState.IN_PROGRESS)
    log.append_transition(Level.TASK, "t1", TaskState.IN_PROGRESS, TaskState.BLOCKED)

    assert task_decisions(log.state, "t1") == [Decision("t1", BLOCKED, "")]


def test_a_log_read_again_gives_the_same_entries(log: EventLog, tmp_path: Path) -> None:
    attempt(log, "t1-a1", said="one", end=S.REJECTED, payload={"reason": "r"})
    attempt(log, "t1-a2", said="two")

    reread = read_state(tmp_path / "events.jsonl", RUN)

    assert task_entries(reread, "t1") == task_entries(log.state, "t1")


def test_a_log_cut_in_the_last_line_gives_the_entries_before_it(
    log: EventLog, tmp_path: Path
) -> None:
    attempt(log, "t1-a1", said="one", end=S.REJECTED, payload={"reason": "r"})
    path = tmp_path / "events.jsonl"
    with path.open("ab") as stream:
        stream.write(b'{"seq": 99, "type": "transi')

    assert task_entries(read_state(path, RUN), "t1") == [
        Entry("t1", "t1-a1", "one", Outcome.REJECTED, "r")
    ]


def rejected(n: int, said: str = "", why: str = "gate 8 (complexity): too complex") -> Entry:
    return Entry("t1", f"t1-a{n}", said, Outcome.REJECTED, why)


def test_no_earlier_attempt_gives_no_text() -> None:
    assert diary_text([]) == ""


def test_a_rejected_attempt_is_shown_with_what_the_agent_said_and_why() -> None:
    text = diary_text([rejected(1, "split f in two")])

    assert text == (
        "### Attempt `t1-a1`: rejected\n"
        "You said: split f in two\n"
        "Why: gate 8 (complexity): too complex\n"
    )


def test_the_three_latest_are_in_full_and_the_older_ones_in_one_line() -> None:
    text = diary_text([rejected(n, f"said {n}") for n in range(1, 6)])

    assert "- `t1-a1`: rejected: gate 8 (complexity): too complex" in text
    assert "- `t1-a2`: rejected: gate 8 (complexity): too complex" in text
    assert "You said: said 1" not in text
    for n in (3, 4, 5):
        assert f"### Attempt `t1-a{n}`: rejected\nYou said: said {n}\n" in text


def test_a_discard_is_one_line_and_does_not_take_a_place_among_the_full_ones() -> None:
    discard = Entry("t1", "t1-a2", "", Outcome.DISCARDED, "network", infrastructure=True)

    text = diary_text([rejected(1, "one"), discard, rejected(3, "three")])

    assert "- `t1-a2`: discarded (infrastructure): network" in text
    assert "### Attempt `t1-a1`: rejected" in text and "### Attempt `t1-a3`: rejected" in text


def test_an_attempt_that_did_not_finish_says_so() -> None:
    assert "### Attempt `t1-a1`: did not finish" in diary_text(
        [Entry("t1", "t1-a1", "", Outcome.OPEN)]
    )


def test_what_the_agent_said_is_cut_and_flattened() -> None:
    text = diary_text([rejected(1, "a\n" + "b" * 400)])

    said = next(line for line in text.splitlines() if line.startswith("You said: "))
    assert len(said) == len("You said: ") + SAID_CUT
    assert said.endswith("...") and "\n" not in said


def test_the_line_of_an_older_attempt_is_cut() -> None:
    text = diary_text([rejected(1, why="x" * 400), *(rejected(n) for n in range(2, 5))])

    line = next(line for line in text.splitlines() if line.startswith("- `t1-a1`"))
    assert len(line) == len("- `t1-a1`: rejected: ") + LINE_CUT and line.endswith("...")


def test_past_the_limit_the_oldest_lines_go_first_and_the_text_says_so() -> None:
    entries = [rejected(n, why="y" * 150) for n in range(1, 60)]

    text = diary_text(entries)

    assert len(text) <= DIARY_LIMIT + 100
    assert text.splitlines()[0] == "25 earlier attempt(s) left out to keep this short."
    assert "### Attempt `t1-a59`: rejected" in text and "`t1-a1`" not in text


def test_when_only_full_entries_are_left_the_oldest_of_them_go() -> None:
    big = [rejected(n, "s" * 300, why="z" * 1500) for n in range(1, 5)]

    text = diary_text(big)

    assert "### Attempt `t1-a4`: rejected" in text


def test_the_text_for_the_attempt_about_to_run_leaves_that_attempt_out(log: EventLog) -> None:
    attempt(log, "t1-a1", said="one", end=S.REJECTED, payload={"reason": "r"})
    attempt(log, "t1-a2", said="two")

    assert "t1-a2" not in stage_diary(log.state, "t1", "t1-a2")
    assert "t1-a1" in stage_diary(log.state, "t1", "t1-a2")
    assert stage_diary(log.state, "t1", "t1-a1").count("Attempt") == 1


def test_a_first_attempt_has_no_diary(log: EventLog) -> None:
    attempt(log, "t1-a1")

    assert stage_diary(log.state, "t1", "t1-a1") == ""


def test_one_rejection_does_not_ask_for_the_hypothesis() -> None:
    assert hypothesis_request([rejected(1)]) == ""


def test_two_rejections_at_the_same_gate_ask_for_the_hypothesis() -> None:
    text = hypothesis_request([rejected(1), rejected(2)])

    assert text == HYPOTHESIS_REQUEST
    assert "share one hypothesis fail the same gate" in text and "`reason`" in text
    assert "premise" not in text.lower()


def test_rejections_at_different_gates_do_not_ask_for_the_hypothesis() -> None:
    other = rejected(2, why="gate 7 (crap): too risky")

    assert hypothesis_request([rejected(1), other]) == ""


def test_the_same_gate_with_another_check_is_not_the_same_place() -> None:
    other = rejected(2, why="gate 8 (coverage): thin")

    assert hypothesis_request([rejected(1), other]) == ""


def test_the_rejections_need_not_follow_each_other() -> None:
    other = rejected(2, why="gate 7 (crap): too risky")

    assert hypothesis_request([rejected(1), other, rejected(3)]) == HYPOTHESIS_REQUEST


def test_a_discard_or_an_approval_never_counts_as_a_rejection() -> None:
    why = "gate 8 (complexity): too complex"
    discarded = Entry("t1", "t1-a2", "", Outcome.DISCARDED, why, infrastructure=True)
    approved = Entry("t1", "t1-a3", "", Outcome.APPROVED, why)

    assert hypothesis_request([rejected(1), discarded, approved]) == ""


def test_a_reason_that_is_not_about_a_gate_does_not_count() -> None:
    assert hypothesis_request([rejected(1, why="no commit"), rejected(2, why="no commit")]) == ""


def test_the_hypothesis_is_asked_for_the_attempt_about_to_run_from_the_log(log: EventLog) -> None:
    for n in (1, 2):
        attempt(log, f"t1-a{n}", end=S.REJECTED, payload={"reason": "gate 8 (complexity): x"})
    attempt(log, "t1-a3")

    assert stage_hypothesis(log.state, "t1", "t1-a3") == HYPOTHESIS_REQUEST
    assert stage_hypothesis(log.state, "t1", "t1-a2") == ""


def test_the_summary_section_says_nothing_happened_when_no_task_ran(log: EventLog) -> None:
    empty = EventLog.open(log.path.with_name("other.jsonl"), RUN, clock=FakeClock())

    assert diary_lines(empty.state) == ["Nenhuma tentativa."]


def test_the_summary_section_lists_each_attempt_and_the_decisions_of_the_forja(
    log: EventLog,
) -> None:
    log.append_transition(Level.TASK, "t1", TaskState.PENDING, TaskState.IN_PROGRESS)
    attempt(log, "t1-a1", said="split f", end=S.REJECTED, payload={"reason": "gate 8 (x): no"})
    attempt(log, "t1-a2", end=S.DISCARDED, payload={"reason": "network", "infra_failure": True})
    attempt(log, "t1-a3")
    log.append_transition(Level.STAGE, "t1", StageState.PENDING, StageState.IN_PROGRESS)
    log.append_transition(Level.STAGE, "t1", StageState.IN_PROGRESS, StageState.EXHAUSTED)
    log.append_transition(Level.TASK, "t1", TaskState.IN_PROGRESS, TaskState.BLOCKED)

    assert diary_lines(log.state) == [
        "- `t1` ():",
        "  - `t1-a1` rejeitada; disse: split f; motivo: gate 8 (x): no",
        "  - `t1-a2` descartada (infraestrutura); motivo: network",
        "  - `t1-a3` não terminou",
        "  - decisão da Forja: etapa esgotada `t1`",
        "  - decisão da Forja: tarefa bloqueada `t1`",
    ]


def test_an_approved_attempt_does_not_list_its_gates_in_the_summary(log: EventLog) -> None:
    attempt(log, "t1-a1", end=S.APPROVED, payload={"gates_passed": ["scope", "lint"]})

    assert diary_lines(log.state) == ["- `t1` ():", "  - `t1-a1` aprovada"]


def test_the_summary_cuts_what_the_agent_said_and_the_reason(log: EventLog) -> None:
    long = "w " * 400
    attempt(log, "t1-a1", said=long, end=S.REJECTED, payload={"reason": long})

    line = diary_lines(log.state)[1]

    assert line.count("...") == 2 and len(line) < 2 * DIARY_CUT + 60
