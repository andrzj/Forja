"""What each part of the installation screen says, as lines of text that never exceed their width.

Pure, like ``panels``: a view, a theme and a size in, lines out, so the content, its width and its
priorities are tested without a terminal. A line that does not fit loses its least important piece
first (the size, then the version, then the bar), never the name of the tool or its stage. The same
final report feeds the full screen, the live line and plain text (``summary_lines``).
"""

from dataclasses import dataclass

from rich.text import Text

from forja.ui.glyphs import Marks, fit, pad, width
from forja.ui.install_events import InstallSummary, InstallView, Stage, ToolRow
from forja.ui.live import clock_text, gauge, percent_text
from forja.ui.panels import _finish, _line, _put, wrapped
from forja.ui.theme import ColorDepth, Role, Theme

STAGE_WORDS = {
    Stage.WAITING: "aguardando",
    Stage.DOWNLOADING: "baixando",
    Stage.CHECKSUM: "conferindo checksum",
    Stage.EXTRACTING: "extraindo",
    Stage.VERIFYING: "verificando",
    Stage.READY: "pronta",
    Stage.PRESENT: "já instalada",
    Stage.FAILED: "falhou",
}
STEPS = (Stage.DOWNLOADING, Stage.CHECKSUM, Stage.EXTRACTING, Stage.VERIFYING)
STAGE_ROLES = {
    Stage.WAITING: Role.MUTED,
    Stage.READY: Role.SUCCESS,
    Stage.PRESENT: Role.INFO,
    Stage.FAILED: Role.ERROR,
}
STAGE_WIDTH = max(width(word) for word in STAGE_WORDS.values())
NAME_WIDTH = 20
VERSION_WIDTH = 10
SIZE_WIDTH = 9
DEFAULT_FIX = "rode forja instalar de novo"
REMOVAL = "Para remover as ferramentas, apague a pasta; a Forja não apaga nada."


View = InstallView


def size_text(size: int) -> str:
    """4300000 as ``4,1 MB``: sizes are read in a glance, with a comma as in Portuguese."""
    if size < 1024:
        return f"{size} B"
    value, unit = size / 1024, "KB"
    for bigger in ("MB", "GB"):
        if value < 1024:
            break
        value, unit = value / 1024, bigger
    return f"{value:.0f} {unit}" if value >= 100 else f"{value:.1f}".replace(".", ",") + f" {unit}"


def stage_mark(stage: Stage, marks: Marks) -> str:
    if stage is Stage.FAILED:
        return marks.failed
    if stage in (Stage.READY, Stage.PRESENT):
        return marks.passed
    return marks.pending if stage is Stage.WAITING else marks.running


def stage_role(stage: Stage) -> Role:
    return STAGE_ROLES.get(stage, Role.WARNING)


def state_word(view: View) -> tuple[str, Role]:
    if not view.started:
        return "preparando", Role.MUTED
    if not view.finished:
        return "instalando", Role.ACCENT
    return ("com falhas", Role.ERROR) if view.summary.failed else ("concluída", Role.SUCCESS)


def _mark_width(marks: Marks) -> int:
    return max(width(mark) for mark in (marks.passed, marks.failed, marks.running, marks.pending))


def percent_of(row: ToolRow) -> str:
    return percent_text(row.progress)


def header(view: View, theme: Theme, columns: int, *, compact: bool) -> list[Text]:
    """Two lines (three when compact): what this is and how far it is, and then, if compact, the
    tool at work, because the compact screen has no panel to say it."""
    word, role = state_word(view)
    right = f"{word} "
    left = fit(
        " FORJA  instalação das ferramentas",
        columns - width(right) - 1,
        ellipsis=theme.glyphs.marks.ellipsis,
    )
    top = _line(columns)
    _put(top, left, theme.style(Role.ACCENT, bold=True))
    _put(top, " " * (columns - width(left) - width(right)), theme.style())
    _put(top, right, theme.style(role, bold=True))
    lines = [_finish(top, columns), overall_line(view, theme, columns)]
    if compact:
        lines.append(current_line(view, theme, columns))
    return lines


def overall_line(view: View, theme: Theme, columns: int, depth: ColorDepth = "truecolor") -> Text:
    """The bar of the whole installation, then how many tools are settled and how long it took."""
    muted = theme.style(Role.MUTED, depth=depth)
    role = Role.ERROR if view.finished and view.summary.failed else Role.ACCENT
    done = f" {view.settled}/{len(view.tools)} ferramentas"

    def build(cells: int, parts: set[str]) -> Text:
        full, empty = gauge(view.fraction, cells, theme.glyphs)
        line = _line(columns)
        _put(line, " total ", muted)
        _put(line, full, theme.style(role, depth=depth))
        _put(line, empty, theme.style(Role.BORDER, depth=depth))
        _put(line, f" {percent_text(view.fraction)}", theme.style(role, depth=depth, bold=True))
        if "count" in parts:
            _put(line, done, muted)
        if "time" in parts:
            _put(line, f" {theme.glyphs.marks.bullet} {clock_text(view.elapsed)}", muted)
        return line

    both = {"count", "time"}
    for cells, parts in ((24, both), (14, both), (10, {"count"}), (8, set())):
        line = build(cells, parts)
        if line.cell_len <= columns:
            return line
    return _finish(build(8, set()), columns)


def current_line(view: View, theme: Theme, columns: int, depth: ColorDepth = "truecolor") -> Text:
    """The tool at work, its stage and how far it is, in one line."""
    marks, ellipsis = theme.glyphs.marks, theme.glyphs.marks.ellipsis
    row = view.focus
    if row is None:
        text = " nada em andamento" if view.started else " preparando a instalação"
        role = Role.MUTED
        mark = ""
    else:
        role = stage_role(row.stage)
        mark = marks.current if row.active else stage_mark(row.stage, marks)
        text = f"{row.info.name} {row.info.version} {marks.bullet} {STAGE_WORDS[row.stage]}"
        if row.stage is Stage.DOWNLOADING:
            text += f" {percent_of(row)}"
    line = _line(columns)
    _put(line, " " + (mark + " " if mark else ""), theme.style(role, depth=depth, bold=True))
    room = columns - width(mark) - 2 if mark else columns - 1
    _put(line, fit(text.strip(), room, ellipsis=ellipsis), theme.style(Role.TEXT, depth=depth))
    return _finish(line, columns)


def _tool_line(row: ToolRow, theme: Theme, columns: int, name_w: int, version_w: int) -> Text:
    marks, ellipsis = theme.glyphs.marks, theme.glyphs.marks.ellipsis
    role = stage_role(row.stage)
    mark = pad(stage_mark(row.stage, marks), _mark_width(marks))
    stage_style = theme.style(role, bold=row.active or row.stage is Stage.FAILED)

    def build(version: bool, cells: int, size: bool) -> Text:
        line = _line(columns)
        _put(line, " " + mark + " ", theme.style(role, bold=row.active))
        _put(line, pad(row.info.name, name_w), theme.style(Role.TEXT, bold=row.active))
        if version:
            _put(line, "  " + pad(row.info.version, version_w), theme.style(Role.MUTED))
        _put(line, "  " + pad(STAGE_WORDS[row.stage], STAGE_WIDTH), stage_style)
        if cells and row.stage is Stage.DOWNLOADING:
            full, empty = gauge(row.progress, cells, theme.glyphs)
            _put(line, "  " + full, theme.style(Role.ACCENT))
            _put(line, empty, theme.style(Role.BORDER))
            _put(line, " " + pad(percent_of(row), 4, align="right"), theme.style(Role.ACCENT))
        elif size:
            _put(line, " " * (cells + 7), theme.style())
        if size:
            _put(
                line,
                "  " + pad(size_text(row.info.size), SIZE_WIDTH, align="right"),
                theme.style(Role.MUTED),
            )
        return line

    for options in ((True, 10, True), (True, 10, False), (False, 10, False), (False, 6, False)):
        line = build(*options)
        line.rstrip()
        if line.cell_len <= columns:
            return line
    room = columns - (_mark_width(marks) + 3) - width(STAGE_WORDS[row.stage]) - 1
    bare = _line(columns)
    _put(bare, " " + mark + " ", theme.style(role))
    if room >= 4:
        _put(bare, fit(row.info.name, room, ellipsis=ellipsis) + " ", theme.style(Role.TEXT))
        _put(bare, STAGE_WORDS[row.stage], stage_style)
    else:
        _put(bare, row.info.name, theme.style(Role.TEXT))
    return _finish(bare, columns)


def _notes(row: ToolRow, theme: Theme, columns: int) -> list[Text]:
    """Under a failed tool: why, and what to do. The compact screen has no other place for it."""
    lines = []
    for label, text in (("motivo", row.reason), ("fazer", row.fix or DEFAULT_FIX)):
        line = _line(columns)
        _put(line, "     ", theme.style())
        _put(line, label + ": ", theme.style(Role.ERROR, bold=True))
        room = columns - 7 - width(label)
        _put(line, fit(text, room, ellipsis=theme.glyphs.marks.ellipsis), theme.style(Role.TEXT))
        lines.append(_finish(line, columns))
    return lines


def tools(view: View, theme: Theme, columns: int, rows: int) -> list[Text]:
    """One line per tool (three for a failed one), the one at work always in view."""
    if not view.tools:
        quiet = _line(columns)
        _put(
            quiet,
            " "
            + fit(
                "nenhuma ferramenta a instalar",
                columns - 1,
                ellipsis=theme.glyphs.marks.ellipsis,
            ),
            theme.style(Role.MUTED),
        )
        return [_finish(quiet, columns)]
    name_w = min(NAME_WIDTH, max(width(row.info.name) for row in view.tools))
    version_w = min(VERSION_WIDTH, max(width(row.info.version) for row in view.tools))
    lines: list[Text] = []
    target = 0
    focus = view.focus
    for row in view.tools:
        if row is focus:
            target = len(lines)
        lines.append(_tool_line(row, theme, columns, name_w, version_w))
        if row.stage is Stage.FAILED:
            lines.extend(_notes(row, theme, columns))
    room = max(rows, 1)
    first = min(max(0, target - room // 3), max(0, len(lines) - room))
    return lines[first : first + room]


def _step_line(stage: Stage, row: ToolRow, theme: Theme, columns: int) -> Text:
    marks = theme.glyphs.marks
    order = STEPS.index(stage)
    if row.stage in (Stage.READY, Stage.PRESENT) or (
        row.stage in STEPS and STEPS.index(row.stage) > order
    ):
        mark, role = marks.passed, Role.SUCCESS
    elif row.stage is stage:
        mark, role = marks.current, Role.WARNING
    else:
        mark, role = marks.pending, Role.MUTED
    line = _line(columns)
    _put(line, " " + mark + " ", theme.style(role, bold=row.stage is stage))
    text = fit(STAGE_WORDS[stage], columns - width(mark) - 2, ellipsis=marks.ellipsis)
    _put(
        line,
        text,
        theme.style(Role.TEXT if role is not Role.MUTED else Role.MUTED, bold=row.stage is stage),
    )
    return _finish(line, columns)


def _fact(label: str, value: str, theme: Theme, columns: int) -> Text:
    line = _line(columns)
    _put(line, " " + pad(label, 8), theme.style(Role.MUTED))
    _put(
        line,
        fit(value, columns - 10, ellipsis=theme.glyphs.marks.ellipsis),
        theme.style(Role.TEXT),
    )
    return _finish(line, columns)


def detail(view: View, theme: Theme, columns: int, rows: int) -> list[Text]:
    """The tool at work: what it is for, where it comes from, the steps and how far it is."""
    row = view.focus
    if row is None:
        return [current_line(view, theme, columns)]
    ellipsis = theme.glyphs.marks.ellipsis
    title = _line(columns)
    _put(
        title,
        " " + fit(f"{row.info.name} {row.info.version}", columns - 1, ellipsis=ellipsis),
        theme.style(Role.ACCENT, bold=True),
    )
    lines = [_finish(title, columns)]
    if row.stage is Stage.FAILED:
        lines += _notes(row, theme, columns)
    elif row.stage is Stage.WAITING:
        lines.append(_fact("etapa", STAGE_WORDS[row.stage], theme, columns))
    else:
        lines += [_step_line(stage, row, theme, columns) for stage in STEPS]
        lines.append(_progress_line(row, theme, columns))
    lines += [
        Text(end=""),
        _fact("função", row.info.purpose, theme, columns),
        _fact("origem", row.info.origin, theme, columns),
        _fact("tamanho", size_text(row.info.size), theme, columns),
    ]
    return lines[: max(rows, 1)]


def _progress_line(row: ToolRow, theme: Theme, columns: int) -> Text:
    """The bar of the download, with the bytes, once the download has started."""
    muted = theme.style(Role.MUTED)

    def build(cells: int, with_bytes: bool) -> Text:
        full, empty = gauge(row.progress, cells, theme.glyphs)
        line = _line(columns)
        _put(line, " ", muted)
        _put(line, full, theme.style(Role.ACCENT))
        _put(line, empty, theme.style(Role.BORDER))
        _put(line, " " + percent_of(row), theme.style(Role.ACCENT, bold=True))
        if with_bytes:
            have = size_text(
                min(row.received, row.info.size)
                if row.stage is Stage.DOWNLOADING
                else row.info.size
            )
            _put(line, f" {have}/{size_text(row.info.size)}", muted)
        return line

    for cells, with_bytes in ((20, True), (12, True), (10, False), (6, False)):
        line = build(cells, with_bytes)
        if line.cell_len <= columns:
            break
    return _finish(line, columns)


@dataclass(frozen=True)
class SummaryLine:
    """One line of the final report: ``kind`` is title, ok, info, fail or hint."""

    kind: str
    text: str


def _names(rows: tuple[ToolRow, ...]) -> str:
    return ", ".join(f"{row.info.name} {row.info.version}" for row in rows)


def summary_lines(view: View) -> list[SummaryLine]:
    """The final report, the same for every layer: what was installed, where and what failed."""
    report: InstallSummary = view.summary
    out: list[SummaryLine] = []
    if not view.tools:
        return [SummaryLine("title", "Nada a instalar: todas as ferramentas já estão presentes.")]
    if report.failed:
        out.append(
            SummaryLine(
                "title",
                f"A instalação terminou com falhas: {len(report.failed)} de "
                f"{len(view.tools)} ferramenta(s) não foram instaladas.",
            )
        )
    elif report.pending:
        out.append(
            SummaryLine(
                "title",
                f"A instalação parou: {len(report.pending)} ferramenta(s) ficaram sem instalar.",
            )
        )
    else:
        out.append(SummaryLine("title", "Instalação concluída."))
    if report.installed:
        out.append(
            SummaryLine("ok", f"Instaladas ({len(report.installed)}): {_names(report.installed)}")
        )
    if report.present:
        out.append(
            SummaryLine("info", f"Já instaladas ({len(report.present)}): {_names(report.present)}")
        )
    if report.installed:
        out.append(SummaryLine("info", f"Onde: {report.destination}"))
    for row in report.failed:
        out.append(
            SummaryLine(
                "fail",
                f"Falhou: {row.info.name} {row.info.version} ({row.info.origin}): {row.reason}",
            )
        )
        out.append(SummaryLine("hint", f"O que fazer: {row.fix or DEFAULT_FIX}"))
    for row in report.pending:
        out.append(SummaryLine("info", f"Não instalada: {row.info.name} {row.info.version}"))
    out.append(SummaryLine("info", f"Tempo: {clock_text(report.elapsed)}"))
    if report.installed:
        out.append(SummaryLine("hint", REMOVAL))
    return out


SUMMARY_ROLES = {
    "ok": Role.SUCCESS,
    "info": Role.TEXT,
    "fail": Role.ERROR,
    "hint": Role.MUTED,
}


def summary(view: View, theme: Theme, columns: int, rows: int, offset: int = 0) -> list[Text]:
    """The final report in the room it has; long lines wrap, ``offset`` scrolls back."""
    marks = theme.glyphs.marks
    failed = bool(view.summary.failed or view.summary.pending)
    out: list[Text] = []
    for item in summary_lines(view):
        role = (
            (Role.ERROR if failed else Role.SUCCESS)
            if item.kind == "title"
            else SUMMARY_ROLES[item.kind]
        )
        mark = {
            "title": marks.failed if failed else marks.passed,
            "ok": marks.passed,
            "fail": marks.failed,
        }.get(item.kind, "")
        lead = " " + pad(mark, _mark_width(marks)) + " "
        room = max(1, columns - width(lead))
        for number, piece in enumerate(wrapped(item.text, room)):
            line = _line(columns)
            _put(line, lead if number == 0 else " " * width(lead), theme.style(role, bold=True))
            _put(
                line,
                piece,
                theme.style(
                    Role.TEXT if item.kind != "hint" else Role.MUTED, bold=item.kind == "title"
                ),
            )
            out.append(_finish(line, columns))
        if item.kind == "title":
            out.append(Text(end=""))
    room = max(1, rows)
    end = len(out) - min(max(0, offset), max(0, len(out) - room))
    return out[max(0, end - room) : end]


def footer(theme: Theme, columns: int, *, finished: bool) -> Text:
    """Only the keys that do something right now."""
    options = (
        (" q sair   t tema   setas rolam o relatório", " q sair   t tema", " q sair")
        if finished
        else (" ctrl+c cancela   t tema", " ctrl+c cancela", " ctrl+c")
    )
    chosen = next((text for text in options if width(text) <= columns), "")
    return _finish(
        Text(pad(chosen, columns), theme.style(Role.BAR_TEXT, Role.BAR), no_wrap=True, end=""),
        columns,
    )


__all__ = [
    "SummaryLine",
    "current_line",
    "detail",
    "footer",
    "header",
    "overall_line",
    "size_text",
    "summary",
    "summary_lines",
    "tools",
]
