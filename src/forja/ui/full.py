"""The full screen: panels laid out by Textual, filled by the pure builders of ``panels``.

Textual decides where every panel goes and how big it is, from the size of the window; each panel
asks the builders for lines that fit the room it was given. So nothing here can put an element
out of place or wider than its panel, and a test that opens the app at many sizes can say so.
The app also is the source of the keys while it runs (``q`` or ``ctrl+k`` stops, ``t`` changes
the theme).
"""

import asyncio
from collections.abc import AsyncIterator
from typing import Any, Protocol, TextIO, cast

from rich.text import Text
from textual import events
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.color import Color
from textual.containers import Horizontal
from textual.widget import Widget

from forja.ui import panels
from forja.ui.terminal import Capabilities, resize_sequences
from forja.ui.theme import Role, Theme, next_theme
from forja.ui.view import View

BORDERS = {"rounded": "round", "single": "solid", "double": "double", "ascii": "ascii"}
SUBJECTS = {
    "tasks": Role.TASKS,
    "attempt": Role.ACTIVITY,
    "rej": Role.REJECTED,
    "final": Role.ACCENT,
    "help": Role.ACCENT,
    "details": Role.ACCENT,
    "log": Role.ACTIVITY,
}
TITLES = {
    "tasks": "Tarefas",
    "attempt": "Tentativa",
    "rej": "Rejeições",
    "final": "Fim da execução",
    "help": "Ajuda",
    "details": "Detalhes da tarefa",
    "log": "Log da atividade",
}
STOP_KEYS = ("ctrl+k", "ctrl+c")
OVERLAYS = {  # pane -> class of the screen that shows it
    "help": "helping",
    "details": "detailing",
    "log": "logging",
}
TOP_FIRST = 10**9  # a scroll back that the pane clamps to its first line


class LinesSource(Protocol):
    """The app a ``Pane`` asks for lines: the run screen and the installation screen are two."""

    def lines_for(self, key: str, width: int, height: int, offset: int) -> list[Text]: ...


class Pane(Widget, can_focus=False):
    """One rectangle of the screen. It asks the app for lines that fit what it was given."""

    BINDINGS = [
        Binding("up", "scroll(1)", show=False),
        Binding("down", "scroll(-1)", show=False),
        Binding("pageup", "scroll(8)", show=False),
        Binding("pagedown", "scroll(-8)", show=False),
        Binding("end", "scroll(0)", show=False),
    ]

    def __init__(self, key: str, *, scrolls: bool = False) -> None:
        super().__init__(id=key)
        self.key = key
        self.back = 0
        self.can_focus = scrolls

    def render(self) -> Text:
        width, height = self.content_size
        screen = cast(LinesSource, self.app)
        lines = screen.lines_for(self.key, width, height, self.back)  # Textual skips empty panes
        return Text(chr(10)).join(lines)  # every line already fits its width

    def action_scroll(self, step: int) -> None:
        self.back = 0 if step == 0 else max(0, self.back + step)
        self.refresh()


def paint_panes(
    app: App[None], theme: Theme, titles: dict[str, str], subjects: dict[str, Role]
) -> None:
    """Paint the screen and every pane in the colors and the border of the theme."""
    background = Color.parse(theme.colors[Role.BACKGROUND])
    text = Color.parse(theme.colors[Role.TEXT])
    border = BORDERS.get(theme.glyphs.name, "round")
    app.screen.styles.background = background
    for pane in app.query(Pane):
        pane.styles.background = background
        pane.styles.color = text
        if pane.key in titles:
            role = subjects[pane.key] if theme.border_by_subject else Role.BORDER
            pane.styles.border = cast(Any, (border, Color.parse(theme.colors[role])))
            pane.border_title = titles[pane.key]
            pane.styles.border_title_color = Color.parse(theme.colors[Role.ACCENT])
            pane.styles.border_title_background = background
        pane.refresh()


class ForjaApp(App[None]):
    ENABLE_COMMAND_PALETTE = False
    CSS = """
    Screen { layout: vertical; overflow: hidden; }
    Pane { border: round white; height: 1fr; }
    #head, #band, #foot { border: none; }
    #head { height: 2; }
    #band { height: 1; display: none; }
    #body { height: 1fr; }
    #tasks { width: 34; }
    #attempt { width: 1fr; }
    #rej { height: 6; }
    #final, #help, #details, #log { display: none; }
    #foot { height: 1; }
    Screen.stopping #band { display: block; }
    Screen.finished #body, Screen.finished #rej { display: none; }
    Screen.finished #final { display: block; }
    Screen.helping #body, Screen.helping #rej, Screen.helping #final { display: none; }
    Screen.helping #help { display: block; }
    Screen.detailing #body, Screen.detailing #rej, Screen.detailing #final { display: none; }
    Screen.detailing #details { display: block; }
    Screen.logging #body, Screen.logging #rej, Screen.logging #final { display: none; }
    Screen.logging #log { display: block; }
    Screen.narrow #tasks { width: 24; }
    Screen.compact #tasks { display: none; }
    Screen.compact #head { height: 3; }
    Screen.compact #rej { height: 3; }
    """
    BINDINGS = [
        Binding("ctrl+k", "stop", priority=True, show=False),
        Binding("ctrl+c", "stop", priority=True, show=False),
        Binding("ctrl+q", "noop", priority=True, show=False),
        Binding("t", "theme", show=False),
        Binding("question_mark", "help", show=False),
        Binding("d", "details", show=False),
        Binding("l", "log", show=False),
        Binding("q", "quit_or_stop", show=False),
        Binding("escape", "leave", show=False),
    ]

    def __init__(self, theme: Theme) -> None:
        super().__init__()
        self.theme_in_use = theme
        self.view: View | None = None
        self.stopping = False
        self.finished = False
        self.final_text: list[str] = []
        self.presses = 0
        self._keys: asyncio.Queue[str] = asyncio.Queue()
        self.layout = panels.layout_for(80, 24)

    # -- the keys, offered to the run ---------------------------------------------------------

    async def keys(self) -> AsyncIterator[str]:
        while True:
            yield await self._keys.get()

    def close(self) -> None:
        pass

    # -- the structure -------------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Pane("head")
        yield Pane("band")
        with Horizontal(id="body"):
            yield Pane("tasks")
            yield Pane("attempt", scrolls=True)
        yield Pane("rej", scrolls=True)
        yield Pane("final")
        yield Pane("help")
        yield Pane("details", scrolls=True)
        yield Pane("log", scrolls=True)
        yield Pane("foot")

    def on_mount(self) -> None:
        self.paint()
        self.arrange(self.size.width, self.size.height)

    def on_resize(self, event: events.Resize) -> None:
        self.arrange(event.size.width, event.size.height)

    def arrange(self, columns: int, rows: int) -> None:
        self.layout = panels.layout_for(columns, rows)
        self.screen.set_class(self.layout.compact, "compact")
        self.screen.set_class(self.layout.narrow, "narrow")
        self.refresh_panes()

    # -- what the run tells the screen ---------------------------------------------------------

    def show(self, view: View) -> None:
        self.view = view
        self.refresh_panes()

    def conclude(self, lines: list[str]) -> None:
        self.final_text = lines
        self.finished = True
        self.stopping = False
        self.screen.set_class(False, "stopping")
        self.screen.set_class(True, "finished")
        self.refresh_panes()

    def refresh_panes(self) -> None:
        if not self.is_running:
            return
        for pane in self.query(Pane):
            pane.refresh()

    def lines_for(self, key: str, width: int, height: int, offset: int) -> list[Text]:
        theme, view = self.theme_in_use, self.view
        if view is None:
            return [Text(" ")]
        if key == "head":
            return panels.header(view, theme, width, compact=self.layout.compact)
        if key == "band":
            return [panels.band(theme, width)]
        if key == "tasks":
            return panels.tasks(view, theme, width, height)
        if key == "attempt":
            return panels.attempt(view, theme, width, height, offset, compact=self.layout.compact)
        if key == "rej":
            return panels.rejections(view, theme, width, height, offset)
        if key == "final":
            return panels.final(self.final_text, view, theme, width, height)
        if key == "help":
            return panels.help_lines(theme, width)
        if key == "details":
            return self._window(key, panels.details(view, theme, width), height)
        if key == "log":
            return self._window(key, panels.log_lines(view, theme, width), height)
        return [panels.footer(theme, width, finished=self.finished, stopping=self.stopping)]

    def _window(self, key: str, lines: list[Text], height: int) -> list[Text]:
        """The part of a long pane in view, its scroll kept between its first and last line."""
        pane = self.query_one(f"#{key}", Pane)
        pane.back = min(pane.back, max(0, len(lines) - height))
        return panels.window(lines, height, pane.back)

    # -- colors --------------------------------------------------------------------------------

    def paint(self) -> None:
        paint_panes(self, self.theme_in_use, TITLES, SUBJECTS)

    def set_theme(self, theme: Theme) -> None:
        self.theme_in_use = theme
        if self.is_running:
            self.paint()

    # -- actions -------------------------------------------------------------------------------

    def action_stop(self) -> None:
        if self.finished:
            self.exit()
            return
        self.presses += 1
        if self.presses == 1:
            self.stopping = True
            self.screen.set_class(True, "stopping")
        self._keys.put_nowait("ctrl+k")
        self.refresh_panes()

    def action_noop(self) -> None:
        pass

    def action_theme(self) -> None:
        self.set_theme(next_theme(self.theme_in_use))

    def action_help(self) -> None:
        self._toggle("help")

    def action_details(self) -> None:
        self._toggle("details", back=TOP_FIRST)

    def action_log(self) -> None:
        self._toggle("log")

    def _toggle(self, key: str, *, back: int = 0) -> None:
        """Open the pane over the run, closing any other, or close it when it is open."""
        opening = not self.screen.has_class(OVERLAYS[key])
        self._close_overlays()
        if opening:
            pane = self.query_one(f"#{key}", Pane)
            pane.back = back
            self.screen.set_class(True, OVERLAYS[key])
            if pane.can_focus:
                pane.focus()
        self.refresh_panes()

    def _overlay_open(self) -> bool:
        return any(self.screen.has_class(name) for name in OVERLAYS.values())

    def _close_overlays(self) -> None:
        for name in OVERLAYS.values():
            self.screen.set_class(False, name)
        self.refresh_panes()

    def action_leave(self) -> None:
        if self._overlay_open():
            self._close_overlays()
        elif self.finished:
            self.exit()

    def action_quit_or_stop(self) -> None:
        """``q`` closes what is open over the run, else stops it safely as ``ctrl+k`` does."""
        if self._overlay_open():
            self._close_overlays()
        else:
            self.action_stop()


class FullRenderer:
    """The ``Renderer`` of the full screen: runs the app beside the run and hands it the views."""

    def __init__(
        self,
        theme: Theme,
        caps: Capabilities,
        *,
        resize: bool = True,
        out: TextIO | None = None,
        headless: bool = False,
    ) -> None:
        import sys  # noqa: PLC0415

        self._app = ForjaApp(theme)
        self._out = out or sys.stdout
        self._sizes = resize_sequences(caps) if resize else None
        self._headless = headless
        self._task: asyncio.Task[None] | None = None

    @property
    def theme(self) -> Theme:
        return self._app.theme_in_use

    @theme.setter
    def theme(self, theme: Theme) -> None:
        self._app.set_theme(theme)

    @property
    def keys_source(self) -> ForjaApp:
        return self._app

    def start(self, view: View) -> None:
        if self._sizes:
            self._out.write(self._sizes[0])
            self._out.flush()
        self._app.show(view)
        self._task = asyncio.create_task(self._app.run_async(headless=self._headless))

    def update(self, view: View) -> None:
        self._app.show(view)

    def stop(self, view: View) -> None:
        self._app.show(view)

    async def finish(self, lines: list[str]) -> None:
        """Show the report and wait for the person to read it and press a key."""
        self._app.conclude(lines)
        await self._wait()

    def abort(self) -> None:
        if self._app.is_running:
            self._app.exit()

    async def closed(self) -> None:
        await self._wait()

    async def _wait(self) -> None:
        try:
            if self._task is not None:
                await self._task
        finally:
            if self._sizes:
                self._out.write(self._sizes[1])
                self._out.flush()
                self._sizes = None
