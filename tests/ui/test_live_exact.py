"""Exact edges of the live area: width boundaries, style flags and what is printed."""

import io

import pytest
from rich.style import Style
from rich.text import Text

from forja.ui.live import HINT, LiveRenderer, render_status
from forja.ui.theme import THEMES, Role
from forja.ui.view import FeedLine
from tests.ui.test_live import busy, caps

THEME = THEMES["escuro"]


def style_of(line: Text, piece: str) -> Style:
    start = line.plain.index(piece)
    for span in line.spans:
        if span.start <= start < span.end:
            assert isinstance(span.style, Style)
            return span.style
    raise AssertionError(piece)


def hint_style(used: int) -> Style:
    style = render_status(busy(tokens_used=used), THEME, 80, "truecolor")[2].spans[-1].style
    assert isinstance(style, Style)
    return style


def test_the_percent_of_the_tokens_is_bold() -> None:
    line = render_status(busy(), THEME, 100, "truecolor")[1]

    assert style_of(line, "43%").bold


def test_the_first_line_is_bold() -> None:
    line = render_status(busy(), THEME, 100, "truecolor")[0]

    assert isinstance(line.style, Style) and line.style.bold


@pytest.mark.parametrize(("running", "tail"), [(0, ""), (1, ""), (2, " \u00b7 +1 em andamento")])
def test_other_tasks_in_progress_are_counted_only_when_there_are_any(
    running: int, tail: str
) -> None:
    view = busy(task_intent="x", tasks_running=running)

    head = render_status(view, THEME, 100, "none")[0].plain

    assert head.endswith(" x" + tail)


def test_the_time_stays_when_the_second_line_fits_exactly_and_goes_one_cell_short() -> None:
    view = busy()
    full = render_status(view, THEME, 200, "none")[1].plain.rstrip()
    size = len(full)

    assert render_status(view, THEME, size, "none")[1].plain == full
    assert render_status(view, THEME, size - 1, "none")[1].plain != full
    assert "12:31" in full
    assert "12:31" not in render_status(view, THEME, size - 1, "none")[1].plain


def test_the_hint_appears_at_the_narrowest_width_that_has_room_for_it() -> None:
    view = busy()

    assert render_status(view, THEME, 31, "none")[2].plain.endswith(HINT)
    assert not render_status(view, THEME, 30, "none")[2].plain.endswith(HINT)


def test_the_hint_is_red_only_when_the_tokens_are_over_the_limit() -> None:
    at_limit = hint_style(1000)
    half = hint_style(500)
    over = hint_style(1001)

    for calm in (at_limit, half):
        assert not calm.bold
        assert str(calm.color).lower() != str(over.color).lower()
    assert over.bold


def test_the_console_is_not_the_legacy_one_and_the_live_area_goes_away_when_it_stops() -> None:
    renderer = LiveRenderer(THEME, caps(), out=io.StringIO())
    assert renderer.console.legacy_windows is False

    renderer.start(busy())

    assert renderer._live is not None
    assert renderer._live.transient is True
    renderer.stop(busy())


def test_what_is_said_is_bold_only_when_asked_and_the_title_is_bold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    renderer = LiveRenderer(THEME, caps(), out=io.StringIO())
    printed: list[Text] = []
    monkeypatch.setattr(renderer.console, "print", lambda text: printed.append(text))

    renderer.say("plain")
    renderer.say("loud", bold=True)
    renderer.start(busy())
    renderer._live.stop()  # type: ignore[union-attr]

    assert [bool(t.style.bold) for t in printed if isinstance(t, Text)] == [False, True, True]  # type: ignore[union-attr]
    assert [t for t in printed if isinstance(t, Text)][2].plain == "Forja · refatorar · meu-servico"


def test_one_new_line_is_printed_and_errors_are_red_while_edits_and_commands_are_not(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    renderer = LiveRenderer(THEME, caps(), out=io.StringIO())
    said: list[tuple[str, Role]] = []
    monkeypatch.setattr(
        renderer, "say", lambda text, role=Role.TEXT, **_: said.append((text, role))
    )

    renderer.update(busy(feed=(FeedLine("12:00:00", "error", "ruim"),), feed_total=1))
    renderer.update(busy(feed=(FeedLine("12:00:01", "edit", "editou a"),), feed_total=2))
    renderer.update(busy(feed=(FeedLine("12:00:02", "command", "rodou b"),), feed_total=3))
    renderer.update(busy(feed=(FeedLine("12:00:03", "text", "pensa"),), feed_total=4))

    assert said == [
        ("12:00:00 ruim", Role.ERROR),
        ("12:00:01 editou a", Role.MUTED),
        ("12:00:02 rodou b", Role.MUTED),
    ]


def test_one_new_rejection_is_printed(monkeypatch: pytest.MonkeyPatch) -> None:
    renderer = LiveRenderer(THEME, caps(), out=io.StringIO())
    said: list[str] = []
    monkeypatch.setattr(renderer, "say", lambda text, role=Role.TEXT, **_: said.append(text))

    renderer.update(busy(feed=(), feed_total=0, rejections=("a",), rejections_total=1))
    renderer.update(busy(feed=(), feed_total=0, rejections=("a", "b"), rejections_total=2))

    assert said == ["✗ a", "✗ b"]
