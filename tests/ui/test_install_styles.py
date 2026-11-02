"""The installation screen at its edges: what is dropped, what is bold, how rows are cut."""

import io
from typing import Any

import pytest
from rich.color import Color
from rich.style import Style
from rich.text import Text

from forja.ui import install_panels as panels
from forja.ui.install_events import InstallModel, InstallStarted, InstallView, Stage, ToolInfo
from forja.ui.install_full import InstallFullRenderer
from forja.ui.install_text import InstallLiveRenderer
from forja.ui.theme import THEMES, Role, with_ascii
from tests.ui.install_support import DESTINATION, MB, VIEWS, at, downloading, played, started
from tests.ui.test_install_panels import plain
from tests.ui.test_live import caps

ESCURO = THEMES["escuro"]
ASCII = with_ascii(ESCURO)


def bold_parts(text: Text) -> str:
    return "".join(
        text.plain[span.start : span.end]
        for span in text.spans
        if isinstance(span.style, Style) and span.style.bold
    )


def color_of(text: Text, needle: str) -> Color | None:
    start = text.plain.index(needle)
    for span in text.spans:
        if isinstance(span.style, Style) and span.start <= start < span.end:
            return span.style.color
    return None


def cells(text: Text) -> int:
    return sum(text.plain.count(char) for char in "#.")


# -- the header ---------------------------------------------------------------------------------


def test_the_title_is_cut_to_leave_the_state_whole_on_the_right() -> None:
    title = " FORJA  instalação das ferramentas"
    view = VIEWS["downloading"]
    top = panels.header(view, ESCURO, 80, compact=False)[0]
    assert top.plain == title + " " * (80 - len(title) - 11) + "instalando "
    assert bold_parts(top) == title + "instalando "
    forty = panels.header(view, ESCURO, 40, compact=False)[0].plain
    assert forty == title[:27] + "… " + "instalando "
    twenty = panels.header(view, ESCURO, 20, compact=False)[0].plain
    assert twenty == title[:7] + "… " + "instalando "
    assert color_of(panels.header(view, ESCURO, 80, compact=False)[0], "instalando") == (
        Color.parse(ESCURO.colors[Role.ACCENT])
    )
    assert color_of(panels.header(view, ESCURO, 80, compact=False)[0], "FORJA") == (
        Color.parse(ESCURO.colors[Role.ACCENT])
    )


# -- the bar of the whole -----------------------------------------------------------------------


def test_the_bar_of_the_whole_keeps_the_biggest_form_that_fits() -> None:
    view = VIEWS["downloading"]

    def bar(columns: int) -> Text:
        return panels.overall_line(view, ASCII, columns)

    assert (cells(bar(58)), bar(58).plain.endswith("00:35")) == (24, True)
    assert (cells(bar(57)), bar(57).plain.endswith("00:35")) == (14, True)
    assert (cells(bar(48)), bar(48).plain.endswith("00:35")) == (14, True)
    assert (cells(bar(47)), bar(47).plain.endswith("ferramentas")) == (10, True)
    assert (cells(bar(36)), bar(36).plain.endswith("ferramentas")) == (10, True)
    assert (cells(bar(35)), bar(35).plain.endswith("3%")) == (8, True)
    assert (cells(bar(18)), bar(18).plain.endswith("3%")) == (8, True)
    assert bar(17).cell_len == 17


def test_the_percent_of_the_whole_is_bold() -> None:
    assert bold_parts(panels.overall_line(VIEWS["downloading"], ESCURO, 120)) == " 3%"


# -- the tool at work ---------------------------------------------------------------------------


def test_the_current_line_leaves_room_for_its_mark() -> None:
    view = VIEWS["downloading"]
    line = panels.current_line(view, ASCII, 20)
    assert line.plain == " > gitleaks 8.21...."
    assert bold_parts(line) == " > "
    assert panels.current_line(VIEWS["done"], ESCURO, 10).plain == " nada em …"
    assert panels.current_line(VIEWS["done"], ESCURO, 80).plain == " nada em andamento"


# -- the rows -----------------------------------------------------------------------------------


def test_the_row_loses_its_pieces_at_these_widths_and_no_other() -> None:
    view = VIEWS["downloading"]

    def first(columns: int) -> str:
        return plain(panels.tools(view, ESCURO, columns, 8))[0]

    assert first(71).endswith("8,0 MB") and "8.21.2" in first(71)
    assert first(70) == " ◔ gitleaks     8.21.2  baixando             ██░░░░░░░░  25%"
    assert first(60) == first(70)
    assert first(59) == " ◔ gitleaks     baixando             ██░░░░░░░░  25%"
    assert first(52) == first(59)
    assert first(51) == " ◔ gitleaks     baixando             ██░░░░  25%"
    assert first(48) == first(51)
    assert first(47) == " ◔ gitleaks baixando"
    assert first(21) == first(47)
    assert first(20) == " ◔ gitlea… baixando"
    assert first(17) == " ◔ git… baixando"
    assert first(16) == " ◔ gitleaks"


def test_the_name_in_the_narrowest_row_gets_what_the_stage_leaves_it() -> None:
    def first(columns: int) -> str:
        return plain(panels.tools(VIEWS["downloading"], ASCII, columns, 8))[0]

    assert first(22) == " [~] gitl... baixando"
    assert first(19) == " [~] g... baixando"
    assert first(18) == " [~] gitleaks"


def test_what_is_bold_in_a_row_is_the_work_and_the_failure() -> None:
    def row_bold(name: str, index: int) -> str:
        return bold_parts(panels.tools(VIEWS[name], ESCURO, 100, 12)[index])

    work = row_bold("downloading", 0)
    assert "gitleaks" in work and "baixando" in work and "semgrep" not in work
    assert "falhou" in row_bold("failed", 1)
    assert row_bold("failed", 0) == ""
    assert row_bold("downloading", 1) == ""


def test_the_notes_under_a_failure_give_the_label_what_the_text_leaves() -> None:
    lines = panels.tools(VIEWS["failed"], ESCURO, 30, 12)
    assert lines[1].plain.startswith(" ✗ semgrep")
    reason = lines[2]
    assert reason.plain == "     motivo: o servidor pypi.…"
    assert bold_parts(reason) == "motivo: "
    assert color_of(reason, "motivo") == Color.parse(ESCURO.colors[Role.ERROR])
    assert lines[3].plain == "     fazer: confira a rede"
    assert panels.tools(VIEWS["failed"], ESCURO, 12, 12)[2].plain == "     motivo…"


def test_the_empty_message_is_cut_with_its_ellipsis() -> None:
    assert panels.tools(InstallView(), ESCURO, 10, 5)[0].plain == " nenhuma …"


def long_view(focus: int, count: int = 30) -> InstallView:
    names = [f"tool{n}" for n in range(count)]
    tools = tuple(ToolInfo(name, name, "p", "1.0", "o", MB) for name in names)
    events: list[Any] = [InstallStarted(tools, DESTINATION)]
    events += [at(name, Stage.READY) for name in names[:focus]]
    events.append(downloading(names[focus], MB // 2))
    return played(*events)


def test_the_window_follows_the_tool_at_work_with_a_third_of_it_before() -> None:
    def names(view: InstallView, rows: int) -> list[str]:
        return [line.split()[1] for line in plain(panels.tools(view, ESCURO, 80, rows))]

    assert names(long_view(0), 6) == [f"tool{n}" for n in range(6)]
    assert names(long_view(1), 6) == [f"tool{n}" for n in range(6)]
    assert names(long_view(2), 6) == [f"tool{n}" for n in range(6)]
    assert names(long_view(3), 6) == [f"tool{n}" for n in range(1, 7)]
    assert names(long_view(20), 6) == [f"tool{n}" for n in range(18, 24)]
    assert names(long_view(29), 6) == [f"tool{n}" for n in range(24, 30)]
    assert names(long_view(20), 9) == [f"tool{n}" for n in range(17, 26)]


def test_a_list_shorter_than_the_room_starts_at_its_first_row() -> None:
    last = played(started(), at("gitleaks", Stage.READY), at("semgrep", Stage.READY),
                  at("osv-scanner", Stage.READY), downloading("jscpd", 1))  # fmt: skip
    shown = plain(panels.tools(last, ESCURO, 80, 5))
    assert [line.split()[1] for line in shown] == ["gitleaks", "semgrep", "osv-scanner", "jscpd"]
    assert plain(panels.tools(VIEWS["done"], ESCURO, 80, 2))[0].startswith(" ✓ gitleaks")
    assert len(panels.tools(VIEWS["done"], ESCURO, 80, 0)) == 1


# -- the detail ---------------------------------------------------------------------------------


def test_the_detail_cuts_each_line_to_the_room_it_has() -> None:
    narrow = plain(panels.detail(VIEWS["verifying"], ESCURO, 14, 14))
    assert narrow[0] == " gitleaks 8.2…"
    assert narrow[2] == " ✓ conferindo…"
    assert narrow[7] == " função  pro…"
    wide = plain(panels.detail(VIEWS["verifying"], ESCURO, 20, 14))
    assert wide[0] == " gitleaks 8.21.2"
    assert wide[2] == " ✓ conferindo check…"
    assert wide[7] == " função  procura s…"
    assert wide[9] == " tamanho 8,0 MB"


def test_the_detail_gives_at_least_one_row_and_its_title_is_bold() -> None:
    assert len(panels.detail(VIEWS["downloading"], ESCURO, 50, 0)) == 1
    title = panels.detail(VIEWS["downloading"], ESCURO, 50, 3)[0]
    assert bold_parts(title) == " gitleaks 8.21.2"
    assert title.plain == " gitleaks 8.21.2"
    short = panels.detail(VIEWS["downloading"], ESCURO, 12, 3)[0].plain
    assert short == " gitleaks 8…"


def test_the_bar_of_the_download_picks_the_biggest_form_that_fits() -> None:
    def bar(columns: int) -> Text:
        return panels.detail(VIEWS["downloading"], ASCII, columns, 14)[5]

    assert (cells(bar(39)), bar(39).plain.endswith("8,0 MB")) == (20, True)
    assert (cells(bar(38)), bar(38).plain.endswith("8,0 MB")) == (12, True)
    assert (cells(bar(31)), bar(31).plain.endswith("8,0 MB")) == (12, True)
    assert (cells(bar(30)), bar(30).plain.endswith("25%")) == (10, True)
    assert (cells(bar(15)), bar(15).plain.endswith("25%")) == (10, True)
    assert (cells(bar(14)), bar(14).plain.endswith("25%")) == (6, True)
    assert (cells(bar(11)), bar(11).plain.endswith("25%")) == (6, True)
    assert bar(10).cell_len == 10
    assert bold_parts(bar(39)) == " 25%"


# -- the report ---------------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["done", "failed", "stopped"])
def test_the_report_wraps_at_every_width_and_never_cuts_with_an_ellipsis(name: str) -> None:
    for columns in range(8, 121):
        for line in panels.summary(VIEWS[name], ESCURO, columns, 100):
            assert line.cell_len <= columns
            assert "…" not in line.plain, (columns, line.plain)


def test_the_report_keeps_every_word_after_wrapping() -> None:
    for columns in (20, 33, 70):
        lines = plain(panels.summary(VIEWS["failed"], ESCURO, columns, 100))
        said = "".join(line.replace("✗", "").replace("✓", "") for line in lines).split()
        wanted = [w for item in panels.summary_lines(VIEWS["failed"]) for w in item.text.split()]
        assert "".join(said) == "".join(wanted)


def test_the_report_marks_titles_bold_and_hints_dim() -> None:
    lines = panels.summary(VIEWS["done"], ESCURO, 100, 30)
    assert lines[0].plain == " ✓ Instalação concluída."
    assert bold_parts(lines[0]) == " ✓ Instalação concluída."
    assert bold_parts(lines[2]) == " ✓ "
    assert color_of(lines[2], "Instaladas") == Color.parse(ESCURO.colors[Role.TEXT])
    assert color_of(lines[-1], "Para remover") == Color.parse(ESCURO.colors[Role.MUTED])
    assert color_of(lines[3], "Já instaladas") == Color.parse(ESCURO.colors[Role.TEXT])
    assert color_of(lines[0], "Instalação") == Color.parse(ESCURO.colors[Role.TEXT])


def test_a_wrapped_line_continues_under_its_text_with_the_lead_blank() -> None:
    lines = plain(panels.summary(VIEWS["failed"], ESCURO, 40, 100))
    index = next(i for i, line in enumerate(lines) if line.startswith(" ✗ Falhou: semgrep"))
    assert lines[index + 1].startswith("     ") and not lines[index + 1].startswith("      ")


def test_the_report_gives_at_least_a_row_and_a_short_report_does_not_scroll() -> None:
    assert len(panels.summary(VIEWS["done"], ESCURO, 80, 0)) == 1
    one = plain(panels.summary(VIEWS["nothing to do"], ESCURO, 80, 10, offset=3))
    assert one[0].startswith(" ✗ Nada a instalar") or one[0].startswith(" ✓ Nada a instalar")
    assert len(one) == 2 or len(one) == 1


def test_the_footer_picks_the_longest_form_that_fits() -> None:
    def foot(columns: int, finished: bool) -> Text:
        return panels.footer(ESCURO, columns, finished=finished)

    assert foot(24, False).plain == " ctrl+c cancela   t tema"
    assert foot(23, False).plain.rstrip() == " ctrl+c cancela"
    assert foot(42, True).plain == " q sair   t tema   setas rolam o relatório"
    assert foot(41, True).plain.rstrip() == " q sair   t tema"
    assert foot(80, False).no_wrap is True
    assert foot(80, True).no_wrap is True
    assert foot(80, False).style == ESCURO.style(Role.BAR_TEXT, Role.BAR)


# -- the weight of the whole --------------------------------------------------------------------


def test_with_two_tools_of_no_size_the_whole_is_counted_by_tools() -> None:
    model = InstallModel()
    model.apply(
        InstallStarted(
            (ToolInfo("a", "a", "", "1", "o", 0), ToolInfo("b", "b", "", "1", "o", 0)), "d"
        )
    )
    model.apply(at("a", Stage.READY))
    assert model.snapshot().fraction == 0.5


# -- the live line and the screen: what the constructors fix -------------------------------------


def test_the_live_renderer_prints_titles_bold_and_the_rest_not() -> None:
    renderer = InstallLiveRenderer(ESCURO, caps(colors="none"), out=io.StringIO())
    printed: list[Text] = []

    def record(item: Any) -> None:
        if isinstance(item, Text):
            printed.append(item)

    renderer.console.print = record  # type: ignore[method-assign,assignment]
    assert renderer.console.legacy_windows is False
    view = played(started(), at("jscpd", Stage.PRESENT))
    renderer.start(view)
    assert renderer._live is not None and renderer._live.transient is True
    assert [bool(isinstance(text.style, Style) and text.style.bold) for text in printed] == [
        True,
        False,
    ]
    printed.clear()
    renderer.say("plain")
    renderer.say_all("plain all")
    assert [bool(isinstance(text.style, Style) and text.style.bold) for text in printed] == [
        False,
        False,
    ]
    printed.clear()
    renderer.stop(played(started(), at("jscpd", Stage.PRESENT)))
    bold = [bool(isinstance(text.style, Style) and text.style.bold) for text in printed]
    assert bold[0] is True and not any(bold[1:])
    assert printed[0].plain.startswith("A instalação parou")


def test_the_full_renderer_is_not_headless_unless_told_to_be() -> None:
    assert InstallFullRenderer(ESCURO)._headless is False
    assert InstallFullRenderer(ESCURO, headless=True)._headless is True


# -- the same edges with the ASCII glyphs, where an ellipsis is three dots and cannot be faked ----


def test_in_ascii_every_cut_is_made_by_the_panel_with_its_own_ellipsis() -> None:
    view = VIEWS["downloading"]
    top = panels.header(view, ASCII, 40, compact=False)[0].plain
    assert top == " FORJA  instalação das fe... instalando "
    assert panels.header(view, ASCII, 12, compact=False)[0].plain == " instalando "
    assert panels.header(view, ASCII, 11, compact=False)[0].plain == "instalando "
    assert panels.current_line(VIEWS["done"], ASCII, 10).plain == " nada e..."
    failed = panels.tools(VIEWS["failed"], ASCII, 30, 12)
    assert failed[2].plain == "     motivo: o servidor pyp..."
    assert panels.tools(VIEWS["failed"], ASCII, 12, 12)[2].plain == "     motivo…"
    assert panels.tools(InstallView(), ASCII, 10, 5)[0].plain == " nenhum..."
    steps = panels.detail(VIEWS["verifying"], ASCII, 14, 14)
    assert [line.plain for line in steps] == [
        " gitleaks 8...",
        " [X] baixando",
        " [X] confer...",
        " [X] extraindo",
        " > verificando",
        " ###### 100%",
        "",
        " função  p...",
        " origem  g...",
        " tamanho 8...",
    ]
    assert panels.detail(VIEWS["downloading"], ASCII, 12, 3)[0].plain == " gitleaks..."


def test_a_window_too_narrow_for_any_key_gets_an_empty_bar() -> None:
    assert panels.footer(ASCII, 5, finished=False).plain == " " * 5
    assert panels.footer(ASCII, 5, finished=True).plain == " " * 5
    assert panels.footer(ASCII, 7, finished=False).plain == " ctrl+c"


def test_a_short_report_stays_whole_however_far_it_is_asked_to_scroll() -> None:
    lines = plain(panels.summary(VIEWS["nothing to do"], ASCII, 80, 10, offset=3))
    assert lines == [" [X] Nada a instalar: todas as ferramentas já estão presentes.", ""]
