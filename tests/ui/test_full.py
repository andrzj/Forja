"""The full screen opened headless at many sizes: every element in place, and the keys."""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from textual.app import App
from textual.geometry import Region

from forja.ui.full import ForjaApp, Pane
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


def test_q_does_nothing_while_the_run_goes_and_leaves_when_it_is_over() -> None:
    async def scenario(app: ForjaApp, pilot: Any) -> None:
        await pilot.press("q")
        await pilot.pause()
        assert app.is_running
        app.conclude(["Entregue em forja-run/x", "Resumo: y"])
        await pilot.pause()
        keys = {pane.key for pane in shown(app)}
        assert "final" in keys and not {"tasks", "attempt", "rej"} & keys
        check_layout(app, (80, 24))
        await pilot.press("q")

    app = drive(THEMES["escuro"], (80, 24), scenario)
    assert not app.is_running


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
