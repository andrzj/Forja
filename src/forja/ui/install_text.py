"""The installation on the live line and in plain text, the two layers that scroll.

``render_status`` is a pure function of a view, a theme and a width, as in ``live``: three lines
that change while the installer works, never wider than the window. ``InstallLiveRenderer`` keeps
them at the bottom of the terminal and prints each tool as it settles; ``InstallPlainRenderer``
prints one line for each thing that happens, with no color and nothing outside the text of the
interface, for logs and pipes. Both end with the same final report as the full screen.
"""

from typing import Protocol, TextIO

from rich.console import Console, Group
from rich.live import Live
from rich.text import Text

from forja.ui.glyphs import clean, fit
from forja.ui.install_events import InstallView, Stage, ToolRow
from forja.ui.install_panels import (
    DEFAULT_FIX,
    STAGE_WORDS,
    SUMMARY_ROLES,
    current_line,
    overall_line,
    percent_of,
    size_text,
    summary_lines,
)
from forja.ui.live import _COLOR_SYSTEM, clock_text
from forja.ui.panels import wrapped
from forja.ui.terminal import Capabilities
from forja.ui.theme import ColorDepth, Role, Theme


class InstallRenderer(Protocol):
    """What the installer drives: the views as they change, and the end."""

    def start(self, view: InstallView) -> None: ...

    def update(self, view: InstallView) -> None: ...

    def stop(self, view: InstallView) -> None: ...


def _queue(view: InstallView, theme: Theme, columns: int, depth: ColorDepth) -> Text:
    waiting = [row.info.name for row in view.tools if row.stage is Stage.WAITING]
    text = f"na fila: {', '.join(waiting)}" if waiting else ""
    return Text(
        " " + fit(text, max(0, columns - 1), ellipsis=theme.glyphs.marks.ellipsis),
        theme.style(Role.MUTED, depth=depth),
    )


def render_status(
    view: InstallView, theme: Theme, columns: int, depth: ColorDepth = "truecolor"
) -> list[Text]:
    """The lines of the live area for a window ``columns`` cells wide."""
    return [
        current_line(view, theme, columns, depth),
        overall_line(view, theme, columns, depth),
        _queue(view, theme, columns, depth),
    ]


def _settled_line(row: ToolRow, theme: Theme) -> tuple[str, Role]:
    marks, name = theme.glyphs.marks, f"{row.info.name} {row.info.version}"
    if row.stage is Stage.FAILED:
        return f"{marks.failed} {name} falhou: {row.reason}", Role.ERROR
    if row.stage is Stage.PRESENT:
        return f"{marks.passed} {name} já instalada", Role.INFO
    return f"{marks.passed} {name} instalada ({size_text(row.info.size)})", Role.SUCCESS


class InstallLiveRenderer:
    """Keeps the live lines at the bottom of the terminal and prints each tool as it settles."""

    def __init__(self, theme: Theme, caps: Capabilities, *, out: TextIO | None = None) -> None:
        self.theme, self.caps = theme, caps
        self.console = Console(
            file=out,
            force_terminal=caps.interactive,
            color_system=_COLOR_SYSTEM[caps.colors],  # type: ignore[arg-type]
            width=caps.columns,
            legacy_windows=False,
        )
        self._live: Live | None = None
        self._said: set[str] = set()

    def _area(self, view: InstallView) -> Group:
        lines = render_status(view, self.theme, self.console.width, self.caps.colors)
        return Group(*lines)

    def say(self, text: str, role: Role = Role.TEXT, *, bold: bool = False) -> None:
        shown = fit(text, self.console.width, ellipsis=self.theme.glyphs.marks.ellipsis)
        self.console.print(Text(shown, self.theme.style(role, depth=self.caps.colors, bold=bold)))

    def say_all(self, text: str, role: Role = Role.TEXT, *, bold: bool = False) -> None:
        """What must be read whole (a reason, a fix): wrapped, not cut."""
        for piece in wrapped(text, self.console.width):
            self.say(piece, role, bold=bold)

    def start(self, view: InstallView) -> None:
        self._live = Live(
            self._area(view), console=self.console, refresh_per_second=8, transient=True
        )
        self._live.start()
        dot = self.theme.glyphs.marks.bullet
        self.say(
            f"Forja {dot} instalação das ferramentas {dot} {len(view.tools)} ferramenta(s) "
            f"em {view.destination}",
            Role.ACCENT,
            bold=True,
        )
        self.update(view)

    def update(self, view: InstallView) -> None:
        for row in view.tools:
            if row.stage in (Stage.READY, Stage.PRESENT, Stage.FAILED) and (
                row.info.key not in self._said
            ):
                self._said.add(row.info.key)
                text, role = _settled_line(row, self.theme)
                self.say_all(text, role)
                if row.stage is Stage.FAILED:
                    self.say_all(f"  o que fazer: {row.fix or DEFAULT_FIX}", Role.MUTED)
        if self._live is not None:
            self._live.update(self._area(view))

    def stop(self, view: InstallView) -> None:
        self.update(view)
        if self._live is not None:
            self._live.stop()
            self._live = None
        for item in summary_lines(view):
            role = Role.ACCENT if item.kind == "title" else SUMMARY_ROLES[item.kind]
            self.say_all(item.text, role, bold=item.kind == "title")


class InstallPlainRenderer:
    """One line for each thing that happens, each beginning with how long it has been going."""

    def __init__(self, out: TextIO) -> None:
        self._out = out
        self._stages: dict[str, Stage] = {}
        self._quarters: dict[str, int] = {}

    def _line(self, view: InstallView, text: str) -> None:
        self._out.write(f"[{clock_text(view.elapsed)}] {clean(text)}\n")
        self._out.flush()

    def start(self, view: InstallView) -> None:
        self._line(view, f"instalação: {len(view.tools)} ferramenta(s) em {view.destination}")
        for row in view.tools:
            info = row.info
            self._line(
                view,
                f"- {info.name} {info.version}: {info.purpose}; origem {info.origin}; "
                f"tamanho {size_text(info.size)}",
            )
        self.update(view)

    def update(self, view: InstallView) -> None:
        for row in view.tools:
            key = row.info.key
            if self._stages.get(key, Stage.WAITING) is not row.stage:
                self._stages[key] = row.stage
                self._entered(view, row)
            elif row.stage is Stage.DOWNLOADING:
                self._download(view, row)

    def _entered(self, view: InstallView, row: ToolRow) -> None:
        name = row.info.name
        if row.stage is Stage.FAILED:
            self._line(view, f"{name}: falhou: {row.reason}")
            self._line(view, f"{name}: o que fazer: {row.fix or DEFAULT_FIX}")
        elif row.stage is Stage.DOWNLOADING:
            self._quarters[row.info.key] = 0
            self._line(view, f"{name}: baixando ({size_text(row.info.size)})")
            self._download(view, row)
        else:
            self._line(view, f"{name}: {STAGE_WORDS[row.stage]}")

    def _download(self, view: InstallView, row: ToolRow) -> None:
        quarter = int(row.progress * 4)
        if quarter > self._quarters[row.info.key]:
            self._quarters[row.info.key] = quarter
            self._line(view, f"{row.info.name}: baixando {percent_of(row)}")

    def stop(self, view: InstallView) -> None:
        self.update(view)
        for item in summary_lines(view):
            self._line(view, item.text)
