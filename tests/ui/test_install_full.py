"""The installation screen opened headless at many sizes: every element in place, and the keys."""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

import pytest

from forja.ui.full import Pane
from forja.ui.install_events import InstallView
from forja.ui.install_full import InstallApp, InstallFullRenderer
from forja.ui.theme import THEMES, Theme, with_ascii
from tests.ui.install_support import VIEWS
from tests.ui.test_full import SIZES, check_layout, shown

Scenario = Callable[[InstallApp, Any], Awaitable[None]]


def drive(
    theme: Theme,
    size: tuple[int, int],
    scenario: Scenario,
    view: InstallView = VIEWS["downloading"],
) -> InstallApp:
    app = InstallApp(theme)

    async def go() -> None:
        async with app.run_test(size=size) as pilot:
            app.show(view)
            await pilot.pause()
            await scenario(app, pilot)
            await pilot.pause()
            if app.is_running:
                check_layout(app, (app.size.width, app.size.height))

    asyncio.run(go())
    return app


async def nothing(app: InstallApp, pilot: Any) -> None:
    return None


def keys_of(app: InstallApp) -> set[str]:
    return {pane.key for pane in shown(app)}


@pytest.mark.parametrize("size", SIZES, ids=lambda size: f"{size[0]}x{size[1]}")
@pytest.mark.parametrize("key", list(THEMES))
def test_every_element_is_in_place_at_every_size_in_every_theme(
    key: str, size: tuple[int, int]
) -> None:
    for theme in (THEMES[key], with_ascii(THEMES[key])):
        drive(theme, size, nothing)


@pytest.mark.parametrize("name", list(VIEWS))
def test_every_moment_of_the_installation_keeps_the_layout(name: str) -> None:
    async def scenario(app: InstallApp, pilot: Any) -> None:
        for size in ((60, 16), (80, 24), (120, 36)):
            await pilot.resize_terminal(*size)
            await pilot.pause()
            check_layout(app, size)
        app.conclude(VIEWS[name])
        await pilot.pause()
        check_layout(app, (120, 36))

    drive(THEMES["neon"], (80, 24), scenario, VIEWS[name])


def test_the_window_can_change_size_while_it_runs() -> None:
    async def scenario(app: InstallApp, pilot: Any) -> None:
        for size in ((60, 16), (120, 36), (80, 24), (200, 60), (60, 16)):
            await pilot.resize_terminal(*size)
            await pilot.pause()
            check_layout(app, size)

    drive(THEMES["escuro"], (120, 36), scenario)


@pytest.mark.parametrize(
    ("size", "compact", "narrow"),
    [
        ((60, 16), True, True),
        ((69, 30), True, True),
        ((80, 19), True, True),
        ((70, 20), False, True),
        ((99, 30), False, True),
        ((100, 30), False, False),
        ((160, 50), False, False),
    ],
)
def test_the_layout_follows_the_widths_of_the_run_screen(
    size: tuple[int, int], compact: bool, narrow: bool
) -> None:
    async def scenario(app: InstallApp, pilot: Any) -> None:
        assert app.layout.compact is compact and app.layout.narrow is narrow
        assert app.screen.has_class("compact") is compact
        assert app.screen.has_class("narrow") is narrow
        assert ("detail" in keys_of(app)) is not compact

    drive(THEMES["escuro"], size, scenario)


def test_a_big_window_shows_the_list_beside_the_tool_at_work() -> None:
    async def scenario(app: InstallApp, pilot: Any) -> None:
        assert keys_of(app) == {"head", "list", "detail", "foot"}
        panes = {pane.key: pane for pane in shown(app)}
        assert panes["detail"].region.width == 46
        assert panes["list"].region.right <= panes["detail"].region.x
        assert panes["head"].region.height == 2

    drive(THEMES["escuro"], (120, 36), scenario)


def test_a_narrow_window_gives_the_detail_less_room_and_a_compact_one_none() -> None:
    async def narrow(app: InstallApp, pilot: Any) -> None:
        detail = next(pane for pane in shown(app) if pane.key == "detail")
        assert detail.region.width == 34

    async def compact(app: InstallApp, pilot: Any) -> None:
        assert keys_of(app) == {"head", "list", "foot"}
        head = next(pane for pane in shown(app) if pane.key == "head")
        assert head.region.height == 3
        text = "\n".join(line.plain for line in app.lines_for("head", 60, 3, 0))
        assert "gitleaks 8.21.2 · baixando 25%" in text

    drive(THEMES["escuro"], (80, 24), narrow)
    drive(THEMES["escuro"], (60, 16), compact)


def test_each_panel_is_filled_from_the_pure_builders() -> None:
    async def scenario(app: InstallApp, pilot: Any) -> None:
        def said(key: str, width: int = 100, height: int = 12) -> str:
            return "\n".join(line.plain for line in app.lines_for(key, width, height, 0))

        assert "instalação das ferramentas" in said("head") and "instalando" in said("head")
        assert "gitleaks" in said("list") and "aguardando" in said("list")
        assert "função" in said("detail") and "origem" in said("detail")
        assert "ctrl+c cancela" in said("foot")
        app.show(VIEWS["done"])
        assert "concluída" in said("head")
        app.conclude(VIEWS["done"])
        assert "Instalação concluída." in said("report")
        assert "q sair" in said("foot")

    drive(THEMES["escuro"], (120, 36), scenario)


def test_the_end_replaces_the_list_with_the_report_until_a_key_is_pressed() -> None:
    async def scenario(app: InstallApp, pilot: Any) -> None:
        app.conclude(VIEWS["failed"])
        await pilot.pause()
        assert keys_of(app) == {"head", "report", "foot"}
        check_layout(app, (80, 24))
        await pilot.press("q")

    app = drive(THEMES["escuro"], (80, 24), scenario)
    assert not app.is_running


def test_q_and_escape_do_nothing_while_the_installer_works_and_leave_when_it_is_over() -> None:
    async def scenario(app: InstallApp, pilot: Any) -> None:
        await pilot.press("q")
        await pilot.press("escape")
        await pilot.pause()
        assert app.is_running
        app.conclude(VIEWS["done"])
        await pilot.pause()
        await pilot.press("escape")

    app = drive(THEMES["escuro"], (80, 24), scenario)
    assert not app.is_running


def test_ctrl_c_is_offered_to_the_installer_while_it_works_and_leaves_at_the_end() -> None:
    async def scenario(app: InstallApp, pilot: Any) -> None:
        await pilot.press("ctrl+c")
        await pilot.pause()
        assert app.is_running and not app.finished

    app = drive(THEMES["escuro"], (80, 24), scenario)
    assert app._keys.get_nowait() == "ctrl+c" and app._keys.empty()

    async def after(app: InstallApp, pilot: Any) -> None:
        app.conclude(VIEWS["done"])
        await pilot.pause()
        await pilot.press("ctrl+c")

    app = drive(THEMES["escuro"], (80, 24), after)
    assert app._keys.empty() and not app.is_running


def test_ctrl_q_is_ignored() -> None:
    async def scenario(app: InstallApp, pilot: Any) -> None:
        await pilot.press("ctrl+q")
        await pilot.pause()
        assert app.is_running

    drive(THEMES["escuro"], (80, 24), scenario)


def test_the_keys_of_the_screen_reach_the_installer_in_order() -> None:
    async def scenario(app: InstallApp, pilot: Any) -> None:
        await pilot.press("ctrl+c", "ctrl+c")
        await pilot.pause()
        source = app.keys()
        assert [await anext(source), await anext(source)] == ["ctrl+c", "ctrl+c"]
        app.close()

    drive(THEMES["escuro"], (80, 24), scenario)


def test_t_changes_the_theme_and_comes_back_around() -> None:
    async def scenario(app: InstallApp, pilot: Any) -> None:
        first = app.theme_in_use.key
        seen = [first]
        for _ in range(len(THEMES)):
            await pilot.press("t")
            await pilot.pause()
            seen.append(app.theme_in_use.key)
            check_layout(app, (80, 24))
        assert seen[-1] == first and len(set(seen)) == len(THEMES)

    drive(THEMES["escuro"], (80, 24), scenario)


def test_the_report_in_focus_scrolls_back_and_returns_to_the_end() -> None:
    async def scenario(app: InstallApp, pilot: Any) -> None:
        app.conclude(VIEWS["failed"])
        await pilot.pause()
        await pilot.press("tab")
        focused = app.focused
        assert isinstance(focused, Pane) and focused.key == "report"
        await pilot.press("pageup")
        assert focused.back == 8
        await pilot.press("end")
        assert focused.back == 0

    drive(THEMES["escuro"], (80, 12), scenario)


def test_the_renderer_runs_the_screen_beside_the_installer_and_waits_for_the_last_key() -> None:
    async def go() -> list[str]:
        renderer = InstallFullRenderer(THEMES["escuro"], headless=True)
        seen: list[str] = []
        renderer.start(VIEWS["queued"])
        app = renderer.keys_source
        for _ in range(100):
            await asyncio.sleep(0.02)
            if app.is_running:
                break
        assert app.is_running
        renderer.update(VIEWS["downloading"])
        seen.append(app.view.tools[0].stage.value)
        renderer.stop(VIEWS["done"])
        seen.append(app.view.tools[0].stage.value)
        finishing = asyncio.create_task(renderer.finish(VIEWS["done"]))
        await asyncio.sleep(0.2)
        assert not finishing.done() and app.finished
        app.exit()
        await finishing
        return seen

    assert asyncio.run(go()) == ["downloading", "ready"]


def test_the_renderer_can_be_aborted_and_closed_even_if_it_never_started() -> None:
    async def go() -> None:
        renderer = InstallFullRenderer(THEMES["escuro"], headless=True)
        renderer.abort()
        await renderer.closed()
        renderer.start(VIEWS["queued"])
        app = renderer.keys_source
        for _ in range(100):
            await asyncio.sleep(0.02)
            if app.is_running:
                break
        renderer.abort()
        await renderer.closed()
        assert not app.is_running

    asyncio.run(go())
