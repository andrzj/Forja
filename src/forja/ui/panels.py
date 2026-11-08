"""What each part of the full screen says, as lines of text that never exceed their width.

Every function here is pure: a view, a theme and a size in, lines out. Nothing depends on Textual,
so the content, its width and its priorities are tested without a terminal. A line that does not
fit is shortened with ``fit`` or loses its least important piece (the time first, then the
attempt), never the tokens, and never breaks a symbol in half.
"""

from collections.abc import Callable
from dataclasses import dataclass

from rich.style import Style
from rich.text import Text

from forja.ui.glyphs import GlyphSet, fit, pad, width
from forja.ui.live import GATE_LABELS, clock_text, gauge, gauge_role, percent_text
from forja.ui.theme import Role, Theme
from forja.ui.view import FeedLine, GateStatus, View, gate_groups

STATE_WORDS = {
    "preparing": "preparando",
    "confirmed": "confirmada",
    "measuring_baseline": "medindo a base",
    "planning": "planejando",
    "executing": "executando",
    "closing": "fechando",
    "paused": "pausada",
    "failed": "falhou",
    "delivered": "entregue",
    "discarded": "descartada",
}
STATE_ROLES = {
    "delivered": Role.SUCCESS,
    "failed": Role.ERROR,
    "paused": Role.WARNING,
    "discarded": Role.MUTED,
}
TASK_ROLES = {
    "integrated": ("passed", Role.SUCCESS),
    "blocked": ("failed", Role.ERROR),
    "in_progress": ("current", Role.WARNING),
}
FEED_ROLES = {"error": Role.ERROR, "edit": Role.TEXT, "text": Role.TEXT}


def short_count(value: int) -> str:
    """680000 as ``680k`` and 2000000 as ``2M``: tokens are read in a glance, not counted."""
    if value >= 1_000_000:
        whole, tenth = divmod(value // 100_000, 10)
        return f"{whole}M" if not tenth else f"{whole}.{tenth}M"
    if value >= 1000:
        return f"{value // 1000}k"
    return str(value)


def state_word(state: str) -> str:
    return STATE_WORDS.get(state, state)


def _line(columns: int) -> Text:
    return Text(no_wrap=True, overflow="ellipsis", end="")


def _put(line: Text, text: str, style: Style) -> None:
    line.append(text, style)


def _finish(line: Text, columns: int) -> Text:
    """The line cut to the width as a last safety, never wider than the window."""
    line.truncate(columns, overflow="ellipsis")
    return line


def header(view: View, theme: Theme, columns: int, *, compact: bool) -> list[Text]:
    """Two lines (three when compact): who and where, then the cost so far."""
    marks, ellipsis = theme.glyphs.marks, theme.glyphs.marks.ellipsis
    state = state_word(view.state)
    state_style = theme.style(STATE_ROLES.get(view.state, Role.ACCENT), bold=True)
    right = f"{state} "
    left_room = max(0, columns - width(right) - 1)
    left = fit(
        f" FORJA  {view.objective} {marks.bullet} {view.repo} {marks.bullet} {view.branch}",
        left_room,
        ellipsis=ellipsis,
    )
    top = _line(columns)
    _put(top, left, theme.style(Role.ACCENT, bold=True))
    _put(top, " " * max(1, columns - width(left) - width(right)), Style())
    _put(top, right, state_style)
    cost = _cost(view, theme, columns, with_attempt=not compact)
    if not compact:
        return [_finish(top, columns), cost]
    task = _line(columns)
    where = f" tarefa {view.number}/{view.tasks_total}"
    if view.attempt:
        where += f" {marks.bullet} tentativa {view.attempt}/{view.attempts_max}"
    _put(task, fit(where, columns, ellipsis=ellipsis), theme.style(Role.TEXT))
    return [_finish(top, columns), _finish(task, columns), cost]


def _cost(view: View, theme: Theme, columns: int, *, with_attempt: bool) -> Text:
    fraction = view.tokens_fraction
    role = gauge_role(fraction)
    muted = theme.style(Role.MUTED)

    def build(cells: int, parts: set[str]) -> Text:
        full, empty = gauge(fraction, cells, theme.glyphs)
        line = _line(columns)
        _put(line, " tokens ", muted)
        _put(line, full, theme.style(role))
        _put(line, empty, theme.style(Role.BORDER))
        _put(line, f" {percent_text(fraction)}", theme.style(role, bold=True))
        if "count" in parts:
            _put(line, f" {short_count(view.tokens_used)}/{short_count(view.tokens_limit)}", muted)
        if "task" in parts and view.task_id:
            _put(
                line, f" {theme.glyphs.marks.bullet} tarefa {short_count(view.task_tokens)}", muted
            )
        if "time" in parts:
            _put(line, f" {theme.glyphs.marks.bullet} tempo {clock_text(view.elapsed)}", muted)
        if "attempt" in parts and view.attempt:
            attempt = f" {theme.glyphs.marks.bullet} tentativa {view.attempt}/{view.attempts_max}"
            _put(line, attempt, muted)
        return line

    wanted = {"count", "task", "time"} | ({"attempt"} if with_attempt else set())
    for cells, parts in (
        (24, wanted), (14, wanted), (10, wanted - {"attempt"}), (10, {"count", "time"}),
        (10, {"count"}), (8, set()),
    ):  # fmt: skip
        line = build(cells, parts)
        if line.cell_len <= columns:
            return line
    return _finish(build(8, set()), columns)


def tasks(view: View, theme: Theme, columns: int, rows: int) -> list[Text]:
    """One line per task with its state, the current one always in view, then the totals."""
    marks, ellipsis = theme.glyphs.marks, theme.glyphs.marks.ellipsis
    room_rows = max(1, rows - 2)
    current = next((i for i, (_, _, st) in enumerate(view.task_rows) if st == "in_progress"), 0)
    first = min(max(0, current - room_rows + 1), max(0, len(view.task_rows) - room_rows))
    lines = []
    for task, intent, state in view.task_rows[first : first + room_rows]:
        name, role = TASK_ROLES.get(state, ("pending", Role.MUTED))
        line = _line(columns)
        _put(line, " " + getattr(marks, name) + " ", theme.style(role, bold=state == "in_progress"))
        text = fit(f"{task} {intent}".strip(), max(1, columns - 4), ellipsis=ellipsis)
        _put(line, text, theme.style(Role.TEXT if state != "pending" else Role.MUTED))
        lines.append(_finish(line, columns))
    summary = _line(columns)
    text = f" {view.tasks_integrated} integrada(s) {marks.bullet} {view.tasks_blocked} bloqueada(s)"
    _put(summary, fit(text, columns, ellipsis=ellipsis), theme.style(Role.MUTED))
    return [*lines, Text(end=""), _finish(summary, columns)][: max(rows, 1)]


def gates_line(view: View, theme: Theme, columns: int) -> Text:
    """The gates of an attempt in order, with names while they fit, then numbers, then symbols."""
    marks = theme.glyphs.marks
    groups = gate_groups(view.gates)
    names = {gate: GATE_LABELS[gate] for gate, _ in groups}
    numbers = {gate: str(gate) for gate, _ in groups}
    for labels in (names, numbers, {gate: "" for gate, _ in groups}):
        line = _line(columns)
        _put(line, " ", Style())
        for position, (gate, status) in enumerate(groups):
            kind, role = {
                GateStatus.PASSED: ("passed", Role.SUCCESS),
                GateStatus.FAILED: ("failed", Role.ERROR),
                GateStatus.RUNNING: ("running", Role.WARNING),
                GateStatus.PENDING: ("pending", Role.MUTED),
            }[status]
            if position:
                _put(line, "  " if labels is names else " ", Style())
            label = labels[gate]
            _put(line, getattr(marks, kind) + (" " + label if label else ""), theme.style(role))
        if line.cell_len <= columns:
            return line
    return _finish(line, columns)


def _feed_line(entry: FeedLine, theme: Theme, columns: int) -> Text:
    line = _line(columns)
    role = FEED_ROLES.get(entry.kind, Role.MUTED)
    _put(line, f" {entry.time} ", theme.style(Role.MUTED))
    room = max(1, columns - width(entry.time) - 2)
    _put(line, fit(entry.text, room, ellipsis=theme.glyphs.marks.ellipsis), theme.style(role))
    return _finish(line, columns)


def attempt(
    view: View, theme: Theme, columns: int, rows: int, offset: int = 0, *, compact: bool = False
) -> list[Text]:
    """The gates of the attempt and, below, what the agent is doing; ``offset`` scrolls back."""
    head = [gates_line(view, theme, columns)]
    if not compact:
        head += [Text(end=""), _title("atividade do agente", theme, columns)]
    room = max(0, rows - len(head))
    feed = list(view.feed)
    end = len(feed) - min(max(0, offset), max(0, len(feed) - room))
    shown = feed[max(0, end - room) : end] if room else []
    body = [_feed_line(entry, theme, columns) for entry in shown]
    if not body and room:
        quiet = _line(columns)
        _put(quiet, " " + fit("aguardando o agente", max(1, columns - 1)), theme.style(Role.MUTED))
        body = [_finish(quiet, columns)]
    return [*head, *body][: max(rows, 1)]


def _title(text: str, theme: Theme, columns: int) -> Text:
    line = _line(columns)
    _put(line, " " + fit(text, max(1, columns - 1)), theme.style(Role.MUTED))
    return _finish(line, columns)


def rejections(view: View, theme: Theme, columns: int, rows: int, offset: int = 0) -> list[Text]:
    """The reasons attempts were refused, newest last; empty is said, not left blank."""
    marks, ellipsis = theme.glyphs.marks, theme.glyphs.marks.ellipsis
    if not view.rejections:
        none = _line(columns)
        _put(
            none,
            " " + fit("nenhuma rejeição até agora", max(1, columns - 1)),
            theme.style(Role.MUTED),
        )
        return [_finish(none, columns)]
    items = list(view.rejections)
    end = len(items) - min(max(0, offset), max(0, len(items) - rows))
    lines = []
    for text in items[max(0, end - rows) : end]:
        line = _line(columns)
        _put(line, f" {marks.failed} ", theme.style(Role.ERROR))
        _put(line, fit(text, max(1, columns - 4), ellipsis=ellipsis), theme.style(Role.TEXT))
        lines.append(_finish(line, columns))
    return lines


def footer(theme: Theme, columns: int, *, finished: bool, stopping: bool) -> Text:
    """Only the keys that do something right now."""
    options: tuple[str, ...]
    if finished:
        options = (" q sair   t tema   ? ajuda", " q sair   t tema", " q sair")
    elif stopping:
        options = (
            " salvando... q de novo sai agora",
            " q de novo sai agora",
            " q: sair",
        )
    else:
        options = (
            " q parar e salvar   t tema   tab painel   setas rolam   ? ajuda",
            " q parar   t tema   tab painel   ? ajuda",
            " q parar   t tema   ? ajuda",
            " q parar",
        )
    chosen = next((text for text in options if width(text) <= columns), options[-1])
    return _finish(
        Text(pad(chosen, columns), theme.style(Role.BAR_TEXT, Role.BAR), no_wrap=True, end=""),
        columns,
    )


def band(theme: Theme, columns: int) -> Text:
    """The strip shown after the first stop: a notice, not a question."""
    text = "Salvando... tudo que já foi feito está guardado. q de novo sai agora."
    shown = pad(text, columns, align="center")
    return _finish(
        Text(shown, theme.style(Role.BACKGROUND, Role.WARNING, bold=True), end=""), columns
    )


def final(lines: list[str], view: View, theme: Theme, columns: int, rows: int) -> list[Text]:
    """The closing report, kept on screen until a key is pressed."""
    marks, ellipsis = theme.glyphs.marks, theme.glyphs.marks.ellipsis
    role = STATE_ROLES.get(view.state, Role.ACCENT)
    out: list[Text] = []
    for number, text in enumerate(lines):
        line = _line(columns)
        _put(
            line,
            " " + (marks.passed + " " if number == 0 and role is Role.SUCCESS else ""),
            theme.style(role, bold=True),
        )
        _put(
            line,
            fit(text, max(1, columns - 3), ellipsis=ellipsis),
            theme.style(Role.TEXT, bold=number == 0),
        )
        out.append(_finish(line, columns))
    stats = _line(columns)
    done = f"{view.tasks_integrated} de {view.tasks_total} tarefa(s) integrada(s)"
    count = (
        f" {done} {marks.bullet} {view.tasks_blocked} bloqueada(s) {marks.bullet} "
        f"tokens {percent_text(view.tokens_fraction)} {marks.bullet} "
        f"tempo {clock_text(view.elapsed)}"
    )
    _put(stats, fit(count, columns, ellipsis=ellipsis), theme.style(Role.MUTED))
    return [*out, Text(end=""), _finish(stats, columns)][: max(rows, 1)]


def help_lines(theme: Theme, columns: int) -> list[Text]:
    keys = (
        (
            "q / ctrl+k / ctrl+c",
            "para, salva tudo e deixa a execução para retomar; de novo sai na hora",
        ),
        ("t", "troca o tema"),
        ("tab", "muda o painel em foco"),
        ("setas, pgup, pgdn", "rolam o painel em foco; end volta ao fim"),
        ("?", "fecha esta ajuda"),
        ("q, esc", "saem, depois que a execução terminou"),
    )
    out = []
    for key, what in keys:
        line = _line(columns)
        _put(line, " " + pad(key, 20), theme.style(Role.ACCENT, bold=True))
        _put(line, fit(what, max(1, columns - 22)), theme.style(Role.TEXT))
        out.append(_finish(line, columns))
    return out


Builder = Callable[..., list[Text]]


@dataclass(frozen=True)
class Layout:
    """Which arrangement a window size gets."""

    compact: bool  # below 70 columns: one column, no task panel
    narrow: bool  # below 100: a narrower task panel


def layout_for(columns: int, rows: int) -> Layout:
    return Layout(compact=columns < 70 or rows < 20, narrow=columns < 100)


__all__ = [
    "GlyphSet",
    "Layout",
    "attempt",
    "band",
    "final",
    "footer",
    "gates_line",
    "header",
    "help_lines",
    "layout_for",
    "rejections",
    "short_count",
    "state_word",
    "tasks",
]
