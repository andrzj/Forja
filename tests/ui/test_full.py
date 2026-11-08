"""The full screen opened headless at many sizes: every element in place, and the keys."""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from textual.app import App
from textual.geometry import Region

from forja.ui import panels
from forja.ui.full import ForjaApp, FullRenderer, Pane
from forja.ui.terminal import Capabilities
from forja.ui.theme import THEMES, Theme, with_ascii
from tests.ui.test_panels import VIEWS

SIZES = [(60, 16), (70, 20), (80, 24), (100, 30), (120, 36), (160, 50), (200, 60)]


def drive(
    theme: Theme, size: tuple[int, int], scenario: Callable[[ForjaApp, Any], Awaitable[None]]
) -> ForjaApp:
    app = ForjaApp(theme)

    async def go() -> None:
        async with app.run_test(size=size) as pilot:
            app.show(VIEWS["busy"])
            await pilot.pause()
            await scenario(app, pilot)
            await pilot.pause()
            if app.is_running:
                check_layout(app, (app.size.width, app.size.height))

    asyncio.run(go())
    return app


async def nothing(app: ForjaApp, pilot: Any) -> None:
    return None


def shown(app: App[None]) -> list[Pane]:
    return [
        pane
        for pane in app.query(Pane)
        if pane.display and all(parent.display for parent in pane.ancestors)
    ]


def overlap(a: Region, b: Region) -> bool:
    return not (
        a.x + a.width <= b.x
        or b.x + b.width <= a.x
        or a.y + a.height <= b.y
        or b.y + b.height <= a.y
    )


def check_layout(app: App[None], size: tuple[int, int]) -> None:
    screen = Region(0, 0, *size)
    panes = shown(app)
    assert panes
    for pane in panes:
        assert pane.region.area > 0, pane.key
        assert screen.contains_region(pane.region), (pane.key, pane.region, size)
    for index, first in enumerate(panes):
        for second in panes[index + 1 :]:
            assert not overlap(first.region, second.region), (first.key, second.key, size)
    assert sum(pane.region.area for pane in panes) == size[0] * size[1], size


@pytest.mark.parametrize("size", SIZES, ids=lambda size: f"{size[0]}x{size[1]}")
@pytest.mark.parametrize("key", list(THEMES))
def test_every_element_is_in_place_at_every_size_in_every_theme(
    key: str, size: tuple[int, int]
) -> None:
    for theme in (THEMES[key], with_ascii(THEMES[key])):
        drive(theme, size, nothing)


@pytest.mark.parametrize("name", list(VIEWS))
def test_hostile_and_empty_views_keep_the_layout(name: str) -> None:
    async def scenario(app: ForjaApp, pilot: Any) -> None:
        app.show(VIEWS[name])
        await pilot.pause()
        check_layout(app, (80, 24))

    drive(THEMES["neon"], (80, 24), scenario)


def test_the_window_can_change_size_while_it_runs() -> None:
    async def scenario(app: ForjaApp, pilot: Any) -> None:
        for size in ((60, 16), (120, 36), (80, 24), (200, 60), (60, 16)):
            await pilot.resize_terminal(*size)
            await pilot.pause()
            check_layout(app, size)

    drive(THEMES["escuro"], (120, 36), scenario)


def test_a_small_window_gets_the_compact_arrangement() -> None:
    async def scenario(app: ForjaApp, pilot: Any) -> None:
        keys = {pane.key for pane in shown(app)}
        assert "tasks" not in keys and {"head", "attempt", "rej", "foot"} <= keys

    drive(THEMES["escuro"], (60, 16), scenario)


def test_a_big_window_shows_every_panel() -> None:
    async def scenario(app: ForjaApp, pilot: Any) -> None:
        assert {pane.key for pane in shown(app)} == {"head", "tasks", "attempt", "rej", "foot"}

    drive(THEMES["escuro"], (120, 36), scenario)


def test_ctrl_k_asks_to_stop_and_shows_the_notice_and_a_second_one_asks_again() -> None:
    async def scenario(app: ForjaApp, pilot: Any) -> None:
        await pilot.press("ctrl+k")
        await pilot.pause()
        assert app.stopping and "band" in {pane.key for pane in shown(app)}
        check_layout(app, (80, 24))
        await pilot.press("ctrl+k")
        await pilot.pause()

    app = drive(THEMES["escuro"], (80, 24), scenario)
    assert [app._keys.get_nowait(), app._keys.get_nowait()] == ["ctrl+k", "ctrl+k"]
    assert app._keys.empty()


def test_ctrl_c_does_the_same_as_ctrl_k() -> None:
    async def scenario(app: ForjaApp, pilot: Any) -> None:
        await pilot.press("ctrl+c")

    app = drive(THEMES["escuro"], (80, 24), scenario)
    assert app._keys.get_nowait() == "ctrl+k"


def test_t_changes_the_theme_and_comes_back_around() -> None:
    async def scenario(app: ForjaApp, pilot: Any) -> None:
        first = app.theme_in_use.key
        seen = [first]
        for _ in range(len(THEMES)):
            await pilot.press("t")
            await pilot.pause()
            seen.append(app.theme_in_use.key)
            check_layout(app, (80, 24))
        assert seen[-1] == first
        assert len(set(seen)) == len(THEMES)

    drive(THEMES["escuro"], (80, 24), scenario)


def test_q_stops_like_ctrl_k_and_a_second_q_asks_again() -> None:
    async def scenario(app: ForjaApp, pilot: Any) -> None:
        await pilot.press("q")
        await pilot.pause()
        assert app.is_running and app.stopping
        assert "band" in {pane.key for pane in shown(app)}
        await pilot.press("q")
        await pilot.pause()

    app = drive(THEMES["escuro"], (80, 24), scenario)
    assert [app._keys.get_nowait(), app._keys.get_nowait()] == ["ctrl+k", "ctrl+k"]
    assert app._keys.empty()


def test_q_with_the_help_open_closes_it_and_does_not_stop() -> None:
    async def scenario(app: ForjaApp, pilot: Any) -> None:
        await pilot.press("question_mark")
        await pilot.pause()
        await pilot.press("q")
        await pilot.pause()
        assert "help" not in {pane.key for pane in shown(app)}
        assert not app.stopping

    app = drive(THEMES["escuro"], (80, 24), scenario)
    assert app._keys.empty()


def test_q_leaves_when_the_run_is_over_without_sending_a_stop() -> None:
    async def scenario(app: ForjaApp, pilot: Any) -> None:
        app.conclude(["Entregue em forja-run/x", "Resumo: y"])
        await pilot.pause()
        keys = {pane.key for pane in shown(app)}
        assert "final" in keys and not {"tasks", "attempt", "rej"} & keys
        check_layout(app, (80, 24))
        await pilot.press("q")

    app = drive(THEMES["escuro"], (80, 24), scenario)
    assert not app.is_running
    assert app._keys.empty()


def test_ctrl_k_after_the_end_leaves_without_sending_a_stop() -> None:
    async def scenario(app: ForjaApp, pilot: Any) -> None:
        app.conclude(["fim"])
        await pilot.pause()
        await pilot.press("ctrl+k")

    app = drive(THEMES["escuro"], (80, 24), scenario)
    assert app._keys.empty()


def test_the_help_opens_and_closes() -> None:
    async def scenario(app: ForjaApp, pilot: Any) -> None:
        await pilot.press("question_mark")
        await pilot.pause()
        assert "help" in {pane.key for pane in shown(app)}
        check_layout(app, (80, 24))
        await pilot.press("escape")
        await pilot.pause()
        assert "help" not in {pane.key for pane in shown(app)}
        check_layout(app, (80, 24))

    drive(THEMES["escuro"], (80, 24), scenario)


def test_l_opens_the_log_at_its_end_scrolls_it_and_closes_it() -> None:
    async def scenario(app: ForjaApp, pilot: Any) -> None:
        await pilot.press("l")
        await pilot.pause()
        keys = {pane.key for pane in shown(app)}
        assert "log" in keys and not {"tasks", "attempt", "rej", "details"} & keys
        check_layout(app, (80, 24))
        pane = app.query_one("#log", Pane)
        assert app.focused is pane and pane.back == 0
        size = pane.content_size
        last = app.lines_for("log", size.width, size.height, pane.back)[-1].plain
        assert "zzz" in last
        await pilot.press("pageup")
        await pilot.pause()
        assert pane.back == 8
        await pilot.press("l")
        await pilot.pause()
        assert "log" not in {pane.key for pane in shown(app)}

    app = drive(THEMES["escuro"], (80, 24), scenario)
    assert app._keys.empty()


@pytest.mark.parametrize("size", SIZES)
def test_the_log_keeps_the_layout_at_every_size(size: tuple[int, int]) -> None:
    async def scenario(app: ForjaApp, pilot: Any) -> None:
        await pilot.press("l")
        await pilot.pause()
        check_layout(app, size)

    drive(THEMES["escuro"], size, scenario)


def test_d_opens_the_details_from_the_top_scrolls_them_and_closes_them() -> None:
    async def scenario(app: ForjaApp, pilot: Any) -> None:
        app.show(VIEWS["rejected task"])
        await pilot.press("d")
        await pilot.pause()
        keys = {pane.key for pane in shown(app)}
        assert "details" in keys and not {"tasks", "attempt", "rej"} & keys
        check_layout(app, (80, 24))
        pane = app.query_one("#details", Pane)
        assert app.focused is pane
        height = pane.content_size.height
        first = app.lines_for("details", pane.content_size.width, height, pane.back)
        assert first[0].plain.startswith(" tarefa t2")
        top = pane.back
        whole = panels.details(VIEWS["rejected task"], app.theme_in_use, pane.content_size.width)
        assert top == len(whole) - height > 0
        await pilot.press("down")
        await pilot.pause()
        assert pane.back == top - 1
        await pilot.press("d")
        await pilot.pause()
        assert "details" not in {pane.key for pane in shown(app)}
        assert "attempt" in {pane.key for pane in shown(app)}

    app = drive(THEMES["escuro"], (80, 24), scenario)
    assert app._keys.empty()


@pytest.mark.parametrize("key", ["q", "escape"])
def test_q_and_escape_close_the_details_without_stopping(key: str) -> None:
    async def scenario(app: ForjaApp, pilot: Any) -> None:
        await pilot.press("d")
        await pilot.pause()
        await pilot.press(key)
        await pilot.pause()
        assert "details" not in {pane.key for pane in shown(app)}
        assert not app.stopping

    app = drive(THEMES["escuro"], (80, 24), scenario)
    assert app._keys.empty()


def test_opening_one_pane_over_the_run_closes_the_other() -> None:
    async def scenario(app: ForjaApp, pilot: Any) -> None:
        await pilot.press("question_mark")
        await pilot.press("d")
        await pilot.pause()
        keys = {pane.key for pane in shown(app)}
        assert "details" in keys and "help" not in keys
        await pilot.press("question_mark")
        await pilot.pause()
        keys = {pane.key for pane in shown(app)}
        assert "help" in keys and "details" not in keys

    drive(THEMES["escuro"], (80, 24), scenario)


@pytest.mark.parametrize("size", SIZES)
def test_the_details_keep_the_layout_at_every_size(size: tuple[int, int]) -> None:
    async def scenario(app: ForjaApp, pilot: Any) -> None:
        app.show(VIEWS["rejected task"])
        await pilot.press("d")
        await pilot.pause()
        check_layout(app, size)

    drive(THEMES["escuro"], size, scenario)


def test_the_details_after_the_end_hide_the_report_until_closed() -> None:
    async def scenario(app: ForjaApp, pilot: Any) -> None:
        app.conclude(["fim"])
        await pilot.pause()
        await pilot.press("d")
        await pilot.pause()
        keys = {pane.key for pane in shown(app)}
        assert "details" in keys and "final" not in keys
        await pilot.press("escape")
        await pilot.pause()
        assert "final" in {pane.key for pane in shown(app)}
        assert app.is_running

    drive(THEMES["escuro"], (80, 24), scenario)


def test_the_panel_in_focus_scrolls_back_and_returns_to_the_end() -> None:
    async def scenario(app: ForjaApp, pilot: Any) -> None:
        await pilot.press("tab")
        focused = app.focused
        assert isinstance(focused, Pane)
        await pilot.press("pageup")
        assert focused.back == 8
        await pilot.press("end")
        assert focused.back == 0
        await pilot.press("down")
        assert focused.back == 0

    drive(THEMES["escuro"], (120, 36), scenario)


def test_the_run_reaches_the_screen_as_it_changes() -> None:
    async def scenario(app: ForjaApp, pilot: Any) -> None:
        app.show(VIEWS["over the limit"])
        await pilot.pause()
        text = "\n".join(line.plain for line in app.lines_for("head", 120, 2, 0))
        assert "130%" in text

    drive(THEMES["escuro"], (120, 36), scenario)


def test_short_details_open_with_no_scroll_left() -> None:
    async def scenario(app: ForjaApp, pilot: Any) -> None:
        await pilot.press("d")
        await pilot.pause()
        pane = app.query_one("#details", Pane)
        size = pane.content_size
        assert len(panels.details(VIEWS["busy"], app.theme_in_use, size.width)) < size.height
        assert pane.back == 0

    drive(THEMES["escuro"], (120, 50), scenario)


def test_only_the_panes_that_scroll_can_take_the_focus() -> None:
    async def scenario(app: ForjaApp, pilot: Any) -> None:
        focusable = {pane.key for pane in app.query(Pane) if pane.can_focus}
        assert focusable == {"attempt", "rej", "details", "log"}

    drive(THEMES["escuro"], (120, 36), scenario)


def test_the_end_of_the_run_takes_down_the_notice_of_a_stop() -> None:
    async def scenario(app: ForjaApp, pilot: Any) -> None:
        await pilot.press("q")
        await pilot.pause()
        app.conclude(["fim"])
        await pilot.pause()
        assert not app.stopping
        assert "band" not in {pane.key for pane in shown(app)}
        footer = app.lines_for("foot", 80, 1, 0)[0].plain
        assert footer.startswith(" q sair")

    drive(THEMES["escuro"], (80, 24), scenario)


def test_the_full_screen_runs_in_the_terminal_unless_asked_to_run_headless() -> None:
    caps = Capabilities(
        interactive=True, colors="truecolor", unicode=True, columns=80, rows=24,
        program="test", dark_background=None, can_resize=False, reduced_motion=False,
    )  # fmt: skip
    renderer = FullRenderer(THEMES["escuro"], caps, resize=False)
    asked: list[object] = []

    async def run_async(**options: object) -> None:
        asked.append(options.get("headless"))

    renderer.keys_source.run_async = run_async  # type: ignore[method-assign]

    async def go() -> None:
        renderer.start(VIEWS["busy"])
        await renderer.closed()

    asyncio.run(go())
    assert asked == [False]
