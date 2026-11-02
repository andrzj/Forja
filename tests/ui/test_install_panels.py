"""What the installation panels say: never wider than their room, only from the closed list."""

import pytest
from rich.color import Color
from rich.text import Text

from forja.ui import install_panels as panels
from forja.ui.glyphs import allowed
from forja.ui.install_events import InstallEvent, InstallFinished, InstallView, Stage, ToolFailed
from forja.ui.theme import THEMES, Role, Theme, with_ascii
from tests.ui.install_support import (
    GITLEAKS,
    MB,
    VIEWS,
    at,
    downloading,
    played,
    started,
    success,
    with_failure,
)

WIDTHS = [1, 5, 12, 20, 30, 40, 58, 60, 61, 79, 80, 99, 100, 119, 120, 140, 200]


def every_panel(view: InstallView, theme: Theme, columns: int, rows: int) -> list[Text]:
    return [
        *panels.header(view, theme, columns, compact=False),
        *panels.header(view, theme, columns, compact=True),
        *panels.tools(view, theme, columns, rows),
        *panels.detail(view, theme, columns, rows),
        *panels.summary(view, theme, columns, rows),
        *panels.summary(view, theme, columns, rows, offset=3),
        panels.current_line(view, theme, columns),
        panels.overall_line(view, theme, columns),
        panels.footer(theme, columns, finished=False),
        panels.footer(theme, columns, finished=True),
    ]


def plain(lines: list[Text]) -> list[str]:
    return [line.plain.rstrip() for line in lines]


@pytest.mark.parametrize("name", list(VIEWS))
@pytest.mark.parametrize("key", list(THEMES))
def test_no_line_is_wider_than_its_room_at_any_width(name: str, key: str) -> None:
    for theme in (THEMES[key], with_ascii(THEMES[key])):
        for columns in WIDTHS:
            for rows in (1, 4, 12):
                for text in every_panel(VIEWS[name], theme, columns, rows):
                    assert text.cell_len <= columns, (name, key, columns, text.plain)


@pytest.mark.parametrize("name", [n for n in VIEWS if n != "hostile"])
def test_only_symbols_from_the_closed_list_are_drawn(name: str) -> None:
    ok = allowed()
    for theme in THEMES.values():
        for columns in (40, 80, 120):
            for text in every_panel(VIEWS[name], theme, columns, 12):
                assert set(text.plain) <= ok, (name, set(text.plain) - ok)


def test_what_a_tool_or_a_failure_says_cannot_move_the_terminal() -> None:
    for columns in (30, 80, 120):
        for text in every_panel(VIEWS["hostile"], THEMES["escuro"], columns, 12):
            assert not set(text.plain) & set("\x1b\x07\r\n\t‮"), text.plain


def test_no_panel_asks_for_more_rows_than_it_was_given() -> None:
    for name, view in VIEWS.items():
        for rows in (1, 2, 5):
            theme = THEMES["escuro"]
            assert len(panels.tools(view, theme, 80, rows)) <= rows, name
            assert len(panels.detail(view, theme, 80, rows)) <= rows, name
            assert len(panels.summary(view, theme, 80, rows)) <= rows, name


# -- the state, the header and the bars ---------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "word", "role"),
    [
        ("not started", "preparando", Role.MUTED),
        ("queued", "instalando", Role.ACCENT),
        ("done", "concluída", Role.SUCCESS),
        ("failed", "com falhas", Role.ERROR),
        ("stopped", "concluída", Role.SUCCESS),
    ],
)
def test_the_state_word_and_its_color(name: str, word: str, role: Role) -> None:
    assert panels.state_word(VIEWS[name]) == (word, role)


def test_the_header_names_the_screen_and_the_state_on_the_right() -> None:
    top, bar = plain(panels.header(VIEWS["downloading"], THEMES["escuro"], 80, compact=False))
    assert top.startswith(" FORJA  instalação das ferramentas")
    assert top.endswith("instalando") and len(top) <= 80
    assert bar == " total ███░░░░░░░░░░░░░░░░░░░░░ 3% 0/4 ferramentas · 00:35".replace(
        "███░", "█░░░"
    )


def test_the_compact_header_adds_the_tool_at_work_because_it_has_no_panel_for_it() -> None:
    lines = plain(panels.header(VIEWS["downloading"], THEMES["escuro"], 60, compact=True))
    assert len(lines) == 3
    assert lines[2] == " ▶ gitleaks 8.21.2 · baixando 25%"
    assert len(plain(panels.header(VIEWS["downloading"], THEMES["escuro"], 60, compact=False))) == 2


def test_the_bar_of_the_whole_drops_the_time_then_the_count_then_shrinks() -> None:
    theme = with_ascii(THEMES["escuro"])
    view = VIEWS["downloading"]

    def bar(columns: int) -> str:
        return panels.overall_line(view, theme, columns).plain

    assert bar(200) == " total #....................... 3% 0/4 ferramentas - 00:35"
    assert bar(53) == " total .............. 3% 0/4 ferramentas - 00:35"
    assert bar(45) == " total .......... 3% 0/4 ferramentas"
    assert bar(30) == " total ........ 3%"
    assert bar(16) == " total ........…"


def test_the_bar_is_red_when_the_end_has_failures_and_accent_otherwise() -> None:
    theme = THEMES["escuro"]

    def colors(view: InstallView) -> set[Color | None]:
        return {span.style.color for span in panels.overall_line(view, theme, 80).spans}  # type: ignore[union-attr]

    error, accent = (Color.parse(theme.colors[role]) for role in (Role.ERROR, Role.ACCENT))
    assert error in colors(VIEWS["failed"]) and accent not in colors(VIEWS["failed"])
    assert error not in colors(VIEWS["done"])
    assert accent in colors(VIEWS["done"])


def test_the_line_of_the_tool_at_work_for_each_moment() -> None:
    theme = with_ascii(THEMES["escuro"])

    def line(name: str, columns: int = 80) -> str:
        return panels.current_line(VIEWS[name], theme, columns).plain

    assert line("not started") == " preparando a instalação"
    assert line("nothing to do") == " nada em andamento"
    assert line("downloading") == " > gitleaks 8.21.2 - baixando 25%"
    assert line("verifying") == " > gitleaks 8.21.2 - verificando"
    assert line("failed") == " [!] semgrep 1.95.0 - falhou"
    assert line("queued") == " [ ] gitleaks 8.21.2 - aguardando"
    assert line("downloading", 12) == " > gitlea..."


# -- the list -------------------------------------------------------------------------------------


def test_the_list_says_each_tool_its_version_its_stage_and_its_size() -> None:
    lines = plain(panels.tools(VIEWS["queued"], THEMES["escuro"], 80, 8))
    assert lines == [
        " · gitleaks     8.21.2  aguardando                               8,0 MB",
        " · semgrep      1.95.0  aguardando                              40,0 MB",
        " · osv-scanner  1.9.1   aguardando                              12,0 MB",
        " · jscpd        4.0.5   aguardando                               2,0 MB",
    ]


def test_a_download_shows_a_bar_with_the_percent_aligned_with_the_rest() -> None:
    lines = plain(panels.tools(VIEWS["downloading"], THEMES["escuro"], 80, 8))
    assert lines[0] == " ◔ gitleaks     8.21.2  baixando             ██░░░░░░░░  25%     8,0 MB"
    assert len({len(line) for line in lines}) == 1


def test_every_stage_has_its_word_and_its_mark() -> None:
    theme = THEMES["escuro"]
    stages = {
        Stage.CHECKSUM: ("◔", "conferindo checksum"),
        Stage.EXTRACTING: ("◔", "extraindo"),
        Stage.VERIFYING: ("◔", "verificando"),
        Stage.READY: ("✓", "pronta"),
        Stage.PRESENT: ("✓", "já instalada"),
    }
    for stage, (mark, word) in stages.items():
        view = played(started(), at("gitleaks", stage))
        first = plain(panels.tools(view, theme, 80, 8))[0]
        assert first.startswith(f" {mark} gitleaks") and word in first, first


def test_what_does_not_fit_is_dropped_by_priority_size_then_version_then_the_bar() -> None:
    view = VIEWS["downloading"]
    theme = THEMES["escuro"]

    def first(columns: int) -> str:
        return plain(panels.tools(view, theme, columns, 8))[0]

    assert first(80).endswith("8,0 MB") and "8.21.2" in first(80)
    assert first(60) == " ◔ gitleaks     8.21.2  baixando             ██░░░░░░░░  25%"
    assert first(59) == " ◔ gitleaks     baixando             ██░░░░░░░░  25%"
    assert first(46) == " ◔ gitleaks baixando"
    assert first(12) == " ◔ gitleaks"
    assert first(11) == " ◔ gitleaks"
    assert first(10) == " ◔ gitlea…"


def test_a_failed_tool_says_why_and_what_to_do_right_under_it() -> None:
    lines = plain(panels.tools(VIEWS["failed"], THEMES["escuro"], 100, 12))
    assert lines[1].startswith(" ✗ semgrep      1.95.0  falhou")
    assert lines[2] == "     motivo: o servidor pypi.org não respondeu (tempo esgotado)"
    assert lines[3] == "     fazer: confira a rede"
    assert lines[5].startswith(" ✗ jscpd        4.0.5   falhou")
    assert lines[7] == "     fazer: rode forja instalar de novo"


def test_the_tool_at_work_stays_in_view_when_the_list_is_longer_than_the_room() -> None:
    names = [f"tool{n}" for n in range(30)]
    tools = tuple(
        GITLEAKS.__class__(name, name, "p", "1.0", "o", MB) for name in names
    )  # fmt: skip
    events: list[InstallEvent] = [started(tools)]
    for name in names[:20]:
        events.append(at(name, Stage.READY))
    events.append(downloading("tool20", MB // 2))
    view = played(*events)
    shown = plain(panels.tools(view, THEMES["escuro"], 80, 6))
    assert len(shown) == 6
    assert any("tool20" in line and "baixando" in line for line in shown)
    assert any("tool19" in line for line in shown)  # a little of what came before
    last = plain(panels.tools(played(*events[:1]), THEMES["escuro"], 80, 6))
    assert "tool0 " in last[0] and "tool5" in last[-1]


def test_an_empty_list_says_so() -> None:
    assert plain(panels.tools(InstallView(), THEMES["escuro"], 80, 5)) == [
        " nenhuma ferramenta a instalar"
    ]


# -- the tool at work ---------------------------------------------------------------------------


def test_the_detail_tells_what_the_tool_is_for_where_it_comes_from_and_how_big() -> None:
    lines = plain(panels.detail(VIEWS["downloading"], THEMES["escuro"], 50, 14))
    assert lines == [
        " gitleaks 8.21.2",
        " ▶ baixando",
        " · conferindo checksum",
        " · extraindo",
        " · verificando",
        " █████░░░░░░░░░░░░░░░ 25% 2,0 MB/8,0 MB",
        "",
        " função  procura segredos no código",
        " origem  github.com/gitleaks/gitleaks",
        " tamanho 8,0 MB",
    ]


def test_the_steps_done_are_checked_and_the_current_one_is_marked() -> None:
    lines = plain(panels.detail(VIEWS["verifying"], THEMES["escuro"], 50, 14))
    assert lines[1:5] == [
        " ✓ baixando",
        " ✓ conferindo checksum",
        " ✓ extraindo",
        " ▶ verificando",
    ]
    assert lines[5] == " ████████████████████ 100% 8,0 MB/8,0 MB"
    mid = plain(
        panels.detail(
            played(started(), downloading("gitleaks", 99 * MB), at("gitleaks", Stage.EXTRACTING)),
            THEMES["escuro"],
            50,
            14,
        )
    )
    assert mid[1:5] == [" ✓ baixando", " ✓ conferindo checksum", " ▶ extraindo", " · verificando"]


def test_the_bar_of_the_download_gets_smaller_before_it_loses_the_bytes() -> None:
    view = VIEWS["downloading"]
    theme = with_ascii(THEMES["escuro"])

    def bar(columns: int) -> str:
        return plain(panels.detail(view, theme, columns, 14))[5]

    assert bar(40) == " #####............... 25% 2,0 MB/8,0 MB"
    assert bar(32) == " ###......... 25% 2,0 MB/8,0 MB"
    assert bar(25) == " ##........ 25%"
    assert bar(10) == " ##.... 2…"


def test_a_tool_that_waits_has_no_steps_yet() -> None:
    lines = plain(panels.detail(VIEWS["queued"], THEMES["escuro"], 50, 14))
    assert lines[:3] == [" gitleaks 8.21.2", " etapa   aguardando", ""]


def test_a_failed_tool_in_the_detail_has_the_reason_and_the_fix_instead_of_the_steps() -> None:
    lines = plain(panels.detail(VIEWS["failed"], THEMES["escuro"], 60, 14))
    assert lines[0] == " semgrep 1.95.0"
    assert lines[1].startswith("     motivo: o servidor pypi.org")
    assert lines[2] == "     fazer: confira a rede"
    assert "verificando" not in "\n".join(lines)


def test_with_nothing_to_show_the_detail_says_nothing_is_going_on() -> None:
    assert plain(panels.detail(VIEWS["done"], THEMES["escuro"], 50, 14)) == [" nada em andamento"]
    assert plain(panels.detail(InstallView(), THEMES["escuro"], 50, 14)) == [
        " preparando a instalação"
    ]


def test_the_least_important_lines_of_the_detail_are_the_ones_cut() -> None:
    lines = plain(panels.detail(VIEWS["downloading"], THEMES["escuro"], 50, 3))
    assert lines == [" gitleaks 8.21.2", " ▶ baixando", " · conferindo checksum"]


# -- the final report ---------------------------------------------------------------------------


def texts(name: str) -> list[tuple[str, str]]:
    return [(item.kind, item.text) for item in panels.summary_lines(VIEWS[name])]


def test_a_good_end_says_what_was_installed_where_and_how_to_remove_it() -> None:
    assert texts("done") == [
        ("title", "Instalação concluída."),
        ("ok", "Instaladas (3): gitleaks 8.21.2, semgrep 1.95.0, osv-scanner 1.9.1"),
        ("info", "Já instaladas (1): jscpd 4.0.5"),
        ("info", "Onde: C:\\Users\\ana\\.forja\\ferramentas"),
        ("info", "Tempo: 00:35"),
        ("hint", "Para remover as ferramentas, apague a pasta; a Forja não apaga nada."),
    ]


def test_an_end_with_failures_says_which_tool_which_origin_why_and_what_to_do() -> None:
    assert texts("failed") == [
        ("title", "A instalação terminou com falhas: 2 de 4 ferramenta(s) não foram instaladas."),
        ("ok", "Instaladas (1): gitleaks 8.21.2"),
        ("info", "Já instaladas (1): osv-scanner 1.9.1"),
        ("info", "Onde: C:\\Users\\ana\\.forja\\ferramentas"),
        (
            "fail",
            "Falhou: semgrep 1.95.0 (pypi.org/project/semgrep): "
            "o servidor pypi.org não respondeu (tempo esgotado)",
        ),
        ("hint", "O que fazer: confira a rede"),
        (
            "fail",
            "Falhou: jscpd 4.0.5 (npmjs.com/package/jscpd): checksum diferente do esperado",
        ),
        ("hint", "O que fazer: rode forja instalar de novo"),
        ("info", "Tempo: 00:35"),
        ("hint", "Para remover as ferramentas, apague a pasta; a Forja não apaga nada."),
    ]


def test_an_installation_that_stopped_says_what_was_left_undone() -> None:
    assert texts("stopped") == [
        ("title", "A instalação parou: 4 ferramenta(s) ficaram sem instalar."),
        ("info", "Não instalada: gitleaks 8.21.2"),
        ("info", "Não instalada: semgrep 1.95.0"),
        ("info", "Não instalada: osv-scanner 1.9.1"),
        ("info", "Não instalada: jscpd 4.0.5"),
        ("info", "Tempo: 00:35"),
    ]


def test_with_nothing_to_install_the_report_says_so_alone() -> None:
    assert texts("nothing to do") == [
        ("title", "Nada a instalar: todas as ferramentas já estão presentes.")
    ]


def test_when_only_tools_already_there_were_found_the_report_does_not_claim_an_install() -> None:
    view = played(
        started(),
        *[at(t, Stage.PRESENT) for t in ("gitleaks", "semgrep", "osv-scanner", "jscpd")],
        InstallFinished(),
    )
    items = panels.summary_lines(view)
    assert [i.kind for i in items] == ["title", "info", "info"]
    assert items[0].text == "Instalação concluída."


def test_the_report_marks_the_title_by_outcome_and_wraps_long_lines() -> None:
    theme = THEMES["escuro"]
    good = plain(panels.summary(VIEWS["done"], theme, 70, 20))
    assert good[0] == " ✓ Instalação concluída."
    assert good[1] == ""
    assert good[2].startswith(" ✓ Instaladas (3): gitleaks 8.21.2, semgrep 1.95.0, osv-scanner")
    bad = plain(panels.summary(VIEWS["failed"], theme, 70, 30))
    assert bad[0].startswith(" ✗ A instalação terminou com falhas")
    assert bad[1].startswith("     ") and bad[1].strip() == "instaladas."
    assert any(line.startswith(" ✗ Falhou: semgrep") for line in bad)
    assert all(len(line) <= 70 for line in bad)
    stopped = plain(panels.summary(VIEWS["stopped"], theme, 100, 30))
    assert stopped[0].startswith(" ✗ A instalação parou")


def test_the_report_scrolls_back_and_never_past_its_ends() -> None:
    theme = THEMES["escuro"]
    everything = plain(panels.summary(VIEWS["failed"], theme, 70, 100))
    end = plain(panels.summary(VIEWS["failed"], theme, 70, 5))
    assert end == everything[-5:]
    back = plain(panels.summary(VIEWS["failed"], theme, 70, 5, offset=2))
    assert back == everything[-7:-2]
    top = plain(panels.summary(VIEWS["failed"], theme, 70, 5, offset=999))
    assert top == everything[:5]
    assert plain(panels.summary(VIEWS["failed"], theme, 70, 5, offset=-4)) == end


def test_the_hostile_text_is_wrapped_and_cut_not_obeyed() -> None:
    lines = plain(panels.summary(VIEWS["hostile"], THEMES["escuro"], 40, 40))
    assert lines and all(len(line.encode("utf-8")) < 4000 for line in lines)
    assert "pwned" in "\n".join(lines)


def test_the_footer_shows_only_the_keys_that_do_something_now() -> None:
    theme = THEMES["escuro"]

    def running(columns: int) -> str:
        return panels.footer(theme, columns, finished=False).plain.rstrip()

    def over(columns: int) -> str:
        return panels.footer(theme, columns, finished=True).plain.rstrip()

    assert running(80) == " ctrl+c cancela   t tema"
    assert running(20) == " ctrl+c cancela"
    assert running(10) == " ctrl+c"
    assert over(80) == " q sair   t tema   setas rolam o relatório"
    assert over(20) == " q sair   t tema"
    assert over(10) == " q sair"
    assert panels.footer(theme, 80, finished=False).cell_len == 80


def test_a_failure_event_without_a_fix_gets_the_default_one() -> None:
    view = played(started(), ToolFailed("gitleaks", "x"), InstallFinished())
    assert panels.summary_lines(view)[2].text == "O que fazer: " + panels.DEFAULT_FIX
    assert panels.DEFAULT_FIX == "rode forja instalar de novo"


def test_the_whole_flow_of_events_never_breaks_a_panel() -> None:
    theme = THEMES["escuro"]
    for events in (success(), with_failure()):
        for upto in range(1, len(events) + 1):
            view = played(*events[:upto])
            for text in every_panel(view, theme, 60, 8):
                assert text.cell_len <= 60
