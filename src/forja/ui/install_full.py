"""The installation on the full screen: panels laid out by Textual, filled by ``install_panels``.

The same rules as the run screen: Textual decides where every panel goes from the size of the
window (the layout is the one of ``panels.layout_for``: narrower below 100 columns, compact below
70 columns or 20 rows), and each panel asks the pure builders for lines that fit its room. While
the installer works the list of tools sits beside the tool at work; at the end the final report
takes their place and stays until a key is pressed.
"""

import asyncio
from collections.abc import AsyncIterator

from rich.text import Text
from textual import events
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal

from forja.ui import install_panels, panels
from forja.ui.full import Pane, paint_panes
from forja.ui.install_events import InstallView
from forja.ui.theme import Role, Theme, next_theme

SUBJECTS = {
    "list": Role.TASKS,
    "detail": Role.ACTIVITY,
    "report": Role.ACCENT,
}
TITLES = {"list": "Ferramentas", "detail": "Em andamento", "report": "Resultado"}


class InstallApp(App[None]):
    ENABLE_COMMAND_PALETTE = False
    CSS = """
    Screen { layout: vertical; overflow: hidden; }
    Pane { border: round white; height: 1fr; }
    #head, #foot { border: none; }
    #head { height: 2; }
    #body { height: 1fr; }
    #list { width: 1fr; }
    #detail { width: 46; }
    #report { display: none; }
    #foot { height: 1; }
    Screen.finished #body { display: none; }
    Screen.finished #report { display: block; }
    Screen.narrow #detail { width: 34; }
    Screen.compact #detail { display: none; }
    Screen.compact #head { height: 3; }
    """
    BINDINGS = [
        Binding("ctrl+c", "cancel", priority=True, show=False),
        Binding("ctrl+q", "noop", priority=True, show=False),
        Binding("t", "theme", show=False),
        Binding("q", "leave", show=False),
        Binding("escape", "leave", show=False),
    ]

    def __init__(self, theme: Theme) -> None:
        super().__init__()
        self.theme_in_use = theme
        self.view = InstallView()
        self.finished = False
        self._keys: asyncio.Queue[str] = asyncio.Queue()
        self.layout = panels.layout_for(80, 24)

    # -- the keys, offered to the installer ----------------------------------------------------

    async def keys(self) -> AsyncIterator[str]:
        while True:
            yield await self._keys.get()

    def close(self) -> None:
        pass

    # -- the structure -------------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Pane("head")
        with Horizontal(id="body"):
            yield Pane("list")
            yield Pane("detail")
        yield Pane("report", scrolls=True)
        yield Pane("foot")

    def on_mount(self) -> None:
        paint_panes(self, self.theme_in_use, TITLES, SUBJECTS)
        self.arrange(self.size.width, self.size.height)

    def on_resize(self, event: events.Resize) -> None:
        self.arrange(event.size.width, event.size.height)

    def arrange(self, columns: int, rows: int) -> None:
        self.layout = panels.layout_for(columns, rows)
        self.screen.set_class(self.layout.compact, "compact")
        self.screen.set_class(self.layout.narrow, "narrow")
        self.refresh_panes()

    # -- what the installer tells the screen ---------------------------------------------------

    def show(self, view: InstallView) -> None:
        self.view = view
        self.refresh_panes()

    def conclude(self, view: InstallView) -> None:
        self.view = view
        self.finished = True
        self.screen.set_class(True, "finished")
        self.refresh_panes()

    def refresh_panes(self) -> None:
        if not self.is_running:
            return
        for pane in self.query(Pane):
            pane.refresh()

    def lines_for(self, key: str, width: int, height: int, offset: int) -> list[Text]:
        theme, view = self.theme_in_use, self.view
        if key == "head":
            return install_panels.header(view, theme, width, compact=self.layout.compact)
        if key == "list":
            return install_panels.tools(view, theme, width, height)
        if key == "detail":
            return install_panels.detail(view, theme, width, height)
        if key == "report":
            return install_panels.summary(view, theme, width, height, offset)
        return [install_panels.footer(theme, width, finished=self.finished)]

    # -- actions -------------------------------------------------------------------------------

    def set_theme(self, theme: Theme) -> None:
        self.theme_in_use = theme
        if self.is_running:
            paint_panes(self, theme, TITLES, SUBJECTS)

    def action_cancel(self) -> None:
        if self.finished:
            self.exit()
        else:
            self._keys.put_nowait("ctrl+c")

    def action_noop(self) -> None:
        pass

    def action_theme(self) -> None:
        self.set_theme(next_theme(self.theme_in_use))

    def action_leave(self) -> None:
        if self.finished:
            self.exit()


class InstallFullRenderer:
    """Runs the app beside the installer and hands it the views."""

    def __init__(self, theme: Theme, *, headless: bool = False) -> None:
        self._app = InstallApp(theme)
        self._headless = headless
        self._task: asyncio.Task[None] | None = None

    @property
    def keys_source(self) -> InstallApp:
        return self._app

    def start(self, view: InstallView) -> None:
        self._app.show(view)
        self._task = asyncio.create_task(self._app.run_async(headless=self._headless))

    def update(self, view: InstallView) -> None:
        self._app.show(view)

    def stop(self, view: InstallView) -> None:
        self._app.show(view)

    async def finish(self, view: InstallView) -> None:
        """Show the report and wait for the person to read it and press a key."""
        self._app.conclude(view)
        await self.closed()

    def abort(self) -> None:
        if self._app.is_running:
            self._app.exit()

    async def closed(self) -> None:
        if self._task is not None:
            await self._task
