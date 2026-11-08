"""Exact values of the view model: counters that start at zero and the edges of the counting."""

from forja.core.states import AttemptState, Level
from forja.ui.view import blank_view
from tests.ui.support import activity, model, progress, transition


def test_an_attempt_without_a_number_in_its_target_counts_up_from_the_last_one() -> None:
    view = model()
    view.apply(transition(Level.ATTEMPT, "t1", AttemptState.CREATED))
    assert view.snapshot().attempt == 1
    view.apply(transition(Level.ATTEMPT, "t1", AttemptState.CREATED))
    assert view.snapshot().attempt == 2


def test_only_the_start_of_a_session_clears_the_message() -> None:
    view = model()
    view.apply(transition(Level.EXECUTION, "r1", "paused", payload={"reason": "interrupted"}))
    view.apply(progress("something_else"))
    assert view.snapshot().message == "interrupted"
    view.apply(progress("session_started"))
    assert view.snapshot().message == ""


def test_a_count_of_one_is_one_and_the_rest_is_zero() -> None:
    view = model()
    view.apply(activity("usage", input=1, output=0))
    assert view.snapshot().tokens_used == 1
    view.apply(activity("usage", input=-3, output=None))
    assert view.snapshot().tokens_used == 1


def test_a_blank_view_is_zero_everywhere() -> None:
    view = blank_view()
    assert (
        view.tasks_total,
        view.tasks_done,
        view.attempt,
        view.attempts_max,
        view.feed_total,
        view.rejections_total,
        view.tokens_used,
        view.tokens_limit,
        view.elapsed,
    ) == (0, 0, 0, 0, 0, 0, 0, 0, 0.0)
