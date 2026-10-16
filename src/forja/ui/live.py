"""The live line: three lines that change as the run goes, and a way to print what must stay.

``render_status`` is a pure function of a view, a theme and a width: it never produces a line
wider than the window, and what does not fit is dropped by priority (the time first, then the
gates, never the tokens) instead of being cut in the middle of a symbol. ``LiveRenderer`` keeps
those lines at the bottom of the terminal and prints the permanent news above them.
"""

from typing import TextIO

from rich.console import Console, Group
from rich.live import Live
from rich.style import Style
from rich.text import Text

from forja.ui.glyphs import GlyphSet, fit, width
from forja.ui.terminal import Capabilities
from forja.ui.theme import ColorDepth, Role, Theme
from forja.ui.view import FeedLine, GateStatus, View

GAUGE_CELLS = 10
HINT = "ctrl+k interrompe"
GATE_NAMES = {
    "scope": "escopo",
    "secrets": "segredos",
    "format": "formato",
    "lint": "lint",
    "build": "build",
    "tests": "testes",
    "complexity": "complex.",
    "mutation": "mutacao",
    "crap": "crap",
}
Pieces = list[tuple[str, Style]]
_COLOR_SYSTEM = {"truecolor": "truecolor", "256": "256", "16": "standard", "none": None}


def clock_text(seconds: float) -> str:
    whole = max(0, int(seconds))
    hours, rest = divmod(whole, 3600)
    if hours:
        return f"{hours}:{rest // 60:02d}:{rest % 60:02d}"
    return f"{rest // 60:02d}:{rest % 60:02d}"


def percent_text(fraction: float) -> str:
    return f"{round(fraction * 100)}%"


def gauge(fraction: float, cells: int, glyphs: GlyphSet) -> tuple[str, str]:
    """The filled and the empty part of a gauge of ``cells`` cells, as two strings."""
    filled = min(cells, max(0, round(fraction * cells)))
    return glyphs.gauge.full * filled, glyphs.gauge.empty * (cells - filled)


def gauge_role(fraction: float) -> Role:
    if fraction > 1:
        return Role.ERROR
    return Role.WARNING if fraction >= 0.7 else Role.TOKENS


_MARK = {
    GateStatus.PASSED: ("passed", Role.SUCCESS),
    GateStatus.FAILED: ("failed", Role.ERROR),
    GateStatus.RUNNING: ("running", Role.WARNING),
    GateStatus.PENDING: ("pending", Role.MUTED),
}


def _gates(view: View, theme: Theme, depth: ColorDepth) -> Pieces:
    pieces: Pieces = []
    for name, status in view.gates:
        mark_name, role = _MARK[status]
        mark = getattr(theme.glyphs.marks, mark_name)
        if pieces:
            pieces.append((" ", Style()))
        pieces.append((f"{mark}{GATE_NAMES[name]}", theme.style(role, depth=depth)))
    return pieces


def _tokens(view: View, theme: Theme, depth: ColorDepth) -> Pieces:
    fraction = view.tokens_fraction
    full, empty = gauge(fraction, GAUGE_CELLS, theme.glyphs)
    role = gauge_role(fraction)
    return [
        ("tokens ", theme.style(Role.MUTED, depth=depth)),
        (full, theme.style(role, depth=depth)),
        (empty, theme.style(Role.BORDER, depth=depth)),
        (f" {percent_text(fraction)}", theme.style(role, depth=depth, bold=True)),
    ]


def _size(pieces: Pieces) -> int:
    return sum(width(text) for text, _ in pieces)


def _join(segments: list[Pieces]) -> Pieces:
    pieces: Pieces = []
    for segment in segments:
        if pieces:
            pieces.append(("  ", Style()))
        pieces.extend(segment)
    return pieces


def _head(view: View, theme: Theme, columns: int, depth: ColorDepth) -> Text:
    marks = theme.glyphs.marks
    if view.tasks_total:
        number = min(view.tasks_done + 1, view.tasks_total)
        text = f"{marks.current} tarefa {number}/{view.tasks_total}"
        if view.attempt:
            text += f" {marks.bullet} tentativa {view.attempt}/{view.attempts_max}"
        if view.task_intent:
            text += f" {marks.bullet} {view.task_intent}"
    else:
        text = f"{marks.current} {view.state}"
        if view.message:
            text += f" {marks.bullet} {view.message}"
    return Text(
        fit(text, columns, ellipsis=marks.ellipsis), theme.style(Role.TEXT, depth=depth, bold=True)
    )


def _second(view: View, theme: Theme, columns: int, depth: ColorDepth) -> Text:
    parts = {
        "gates": _gates(view, theme, depth),
        "tokens": _tokens(view, theme, depth),
        "time": [(clock_text(view.elapsed), theme.style(Role.MUTED, depth=depth))],
    }
    show = ["gates", "tokens", "time"]
    for drop in ("time", "gates"):
        if _size(_join([parts[name] for name in show])) <= columns:
            break
        show.remove(drop)
    line = Text.assemble(*_join([parts[name] for name in show]))
    line.truncate(columns, overflow="ellipsis")
    return line


def _feed_role(line: FeedLine | None) -> Role:
    if line is None:
        return Role.MUTED
    return {"error": Role.ERROR, "edit": Role.TEXT}.get(line.kind, Role.MUTED)


def _third(view: View, theme: Theme, columns: int, depth: ColorDepth) -> Text:
    line = view.feed[-1] if view.feed else None
    left = f"{line.time} {line.text}" if line else ""
    ellipsis = theme.glyphs.marks.ellipsis
    room = columns - width(HINT) - 2
    if room < 12:  # too narrow for both: the news matters more
        return Text(fit(left, columns, ellipsis=ellipsis), theme.style(Role.MUTED, depth=depth))
    text = Text(fit(left, room, ellipsis=ellipsis), theme.style(_feed_role(line), depth=depth))
    text.append(" " * (columns - text.cell_len - width(HINT)))
    over = view.tokens_fraction > 1
    text.append(HINT, theme.style(Role.ERROR if over else Role.MUTED, depth=depth, bold=over))
    return text


def render_status(
    view: View, theme: Theme, columns: int, depth: ColorDepth = "truecolor"
) -> list[Text]:
    """The lines of the live area for a window ``columns`` cells wide."""
    return [
        _head(view, theme, columns, depth),
        _second(view, theme, columns, depth),
        _third(view, theme, columns, depth),
    ]


class LiveRenderer:
    """Keeps the live lines at the bottom of the terminal and prints the news above them."""

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
        self._printed = 0
        self._rejected = 0

    def _area(self, view: View) -> Group:
        lines = render_status(view, self.theme, self.console.width, self.caps.colors)
        return Group(*lines)

    def start(self, view: View) -> None:
        self._live = Live(
            self._area(view), console=self.console, refresh_per_second=8, transient=True
        )
        self._live.start()
        dot = self.theme.glyphs.marks.bullet
        self.say(f"Forja {dot} {view.objective} {dot} {view.repo}", Role.ACCENT, bold=True)

    def say(self, text: str, role: Role = Role.TEXT, *, bold: bool = False) -> None:
        shown = fit(text, self.console.width, ellipsis=self.theme.glyphs.marks.ellipsis)
        self.console.print(Text(shown, self.theme.style(role, depth=self.caps.colors, bold=bold)))

    def update(self, view: View) -> None:
        new = min(view.feed_total - self._printed, len(view.feed))
        for line in view.feed[len(view.feed) - new :] if new > 0 else ():
            if line.kind in ("edit", "error", "command"):
                role = Role.ERROR if line.kind == "error" else Role.MUTED
                self.say(f"{line.time} {line.text}", role)
        self._printed = view.feed_total
        fresh = min(view.rejections_total - self._rejected, len(view.rejections))
        for rejection in view.rejections[len(view.rejections) - fresh :] if fresh > 0 else ():
            self.say(f"{self.theme.glyphs.marks.failed} {rejection}", Role.ERROR)
        self._rejected = view.rejections_total
        if self._live is not None:
            self._live.update(self._area(view))

    def stop(self, view: View) -> None:
        if self._live is not None:
            self._live.stop()
            self._live = None
        self.say(f"{view.state}: {view.message}" if view.message else view.state, Role.ACCENT)
