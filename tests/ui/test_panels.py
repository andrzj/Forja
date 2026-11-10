"""What the panels say: never wider than their room, only from the closed list of symbols."""

import pytest
from rich.text import Text

from forja.ui import panels
from forja.ui.glyphs import allowed, width
from forja.ui.theme import THEMES, Role, Theme, with_ascii
from forja.ui.view import FeedLine, GateStatus, View, blank_view
from tests.ui.test_live import busy

WIDTHS = [1, 5, 12, 20, 30, 40, 58, 60, 61, 79, 80, 99, 100, 119, 120, 140, 200]
HOSTILE = "\x1b]0;pwned\x07\x1b[2J" + "界" * 30 + "‮\u0007tail\n\r\t"


def view(**changes: object) -> View:
    rows = (
        ("t1", "reduzir label (CCN 19)", "integrated"),
        ("t2", "reduzir parse_args (CCN 17)", "in_progress"),
        ("t3", "reduzir render (CCN 16)", "pending"),
        ("t4", "reduzir " + "x" * 120, "blocked"),
    )
    feed = tuple(
        FeedLine(f"12:00:{n:02d}", "edit" if n % 2 else "read", f"leu src/a{n}.py")
        for n in range(40)
    )
    base: dict[str, object] = dict(
        task_rows=rows, feed=feed, tasks_integrated=1, tasks_blocked=1,
        log=(*feed, FeedLine("12:01:00", "error", "falhou " + "z" * 150)),
        rejections=("t2-a1: format " + "y" * 200, "t2-a2: lint"),
        tokens_used=680_000, tokens_limit=2_000_000, elapsed=761.0,
    )  # fmt: skip
    return busy(**{**base, **changes})


VIEWS = {
    "busy": view(),
    "empty": blank_view(),
    "hostile": view(task_intent=HOSTILE, objective=HOSTILE, repo=HOSTILE),
    "over the limit": view(tokens_used=2_600_000),
    "failed gate": view(gates=(("scope", GateStatus.FAILED),) + view().gates[1:]),
    "rejected task": view(task_id="t2", task_intent=HOSTILE + " " + "palavra " * 40),
}


def every_panel(
    shown: View,
    theme: Theme,
    columns: int,
    rows: int,
    report: tuple[str, ...] = ("Entregue", "Branch: x"),
) -> list[Text]:
    compact = columns < 70
    return [
        *panels.header(shown, theme, columns, compact=compact),
        *panels.tasks(shown, theme, columns, rows),
        *panels.attempt(shown, theme, columns, rows, compact=compact),
        *panels.attempt(shown, theme, columns, rows, offset=5, compact=compact),
        *panels.rejections(shown, theme, columns, rows),
        panels.footer(theme, columns, finished=False, stopping=False),
        panels.footer(theme, columns, finished=False, stopping=True),
        panels.footer(theme, columns, finished=True, stopping=False),
        panels.band(theme, columns),
        *panels.final(list(report), shown, theme, columns, rows),
        *panels.help_lines(theme, columns),
        *panels.details(shown, theme, columns),
        *panels.log_lines(shown, theme, columns),
    ]


@pytest.mark.parametrize("name", list(VIEWS))
@pytest.mark.parametrize("key", list(THEMES))
def test_no_line_is_wider_than_its_room_at_any_width(name: str, key: str) -> None:
    for theme in (THEMES[key], with_ascii(THEMES[key])):
        for columns in WIDTHS:
            for text in every_panel(VIEWS[name], theme, columns, 12, ("Entregue", HOSTILE)):
                assert text.cell_len <= columns, (name, key, columns, text.plain)


@pytest.mark.parametrize("name", [n for n in VIEWS if n not in ("hostile", "rejected task")])
def test_only_symbols_from_the_closed_list_are_drawn(name: str) -> None:
    ok = allowed()
    for theme in THEMES.values():
        for columns in (40, 80, 120):
            for text in every_panel(VIEWS[name], theme, columns, 12):
                assert set(text.plain) <= ok, (name, set(text.plain) - ok)


def test_no_panel_has_more_lines_than_rows() -> None:
    theme = THEMES["escuro"]
    for rows in (1, 2, 3, 5, 12, 30):
        assert len(panels.tasks(VIEWS["busy"], theme, 40, rows)) <= rows
        assert len(panels.attempt(VIEWS["busy"], theme, 40, rows)) <= rows
        assert len(panels.rejections(VIEWS["busy"], theme, 40, rows)) <= rows
        assert len(panels.final(["a", "b"], VIEWS["busy"], theme, 40, rows)) <= rows


def test_the_tokens_survive_when_everything_else_is_dropped() -> None:
    theme = THEMES["escuro"]
    for columns in (60, 40, 30, 24):
        assert "%" in panels.header(VIEWS["busy"], theme, columns, compact=False)[1].plain


def test_a_wide_header_says_count_time_and_attempt() -> None:
    plain = panels.header(VIEWS["busy"], THEMES["escuro"], 120, compact=False)[1].plain
    assert "680k/2M" in plain and "tempo 12:41" in plain and "tentativa 1/3" in plain


def test_the_header_says_the_tokens_of_the_task_and_drops_them_before_the_time() -> None:
    shown = view(task_tokens=120_000)

    def cost(columns: int) -> str:
        return panels.header(shown, THEMES["escuro"], columns, compact=True)[2].plain

    assert cost(120) == (" tokens ████████░░░░░░░░░░░░░░░░ 34% 680k/2M · tarefa 120k · tempo 12:41")
    widest_without = next(c for c in range(120, 0, -1) if "tarefa" not in cost(c))
    assert "680k/2M · tempo 12:41" in cost(widest_without)


def test_before_any_task_the_header_has_no_task_tokens() -> None:
    plain = panels.header(view(task_id=""), THEMES["escuro"], 200, compact=False)[1].plain
    assert "tarefa" not in plain and "tempo" in plain


def test_the_compact_header_has_three_lines() -> None:
    assert len(panels.header(VIEWS["busy"], THEMES["escuro"], 60, compact=True)) == 3


def test_the_current_task_stays_in_view_when_the_list_is_long() -> None:
    rows = tuple(
        (f"t{n}", f"tarefa {n}", "in_progress" if n == 30 else "pending") for n in range(1, 41)
    )
    shown = panels.tasks(view(task_rows=rows), THEMES["escuro"], 40, 6)
    assert any("t30" in line.plain for line in shown[:-2])


def test_scrolling_back_shows_older_lines_and_cannot_go_past_the_start() -> None:
    theme = THEMES["escuro"]
    tail = panels.attempt(VIEWS["busy"], theme, 60, 8)[-1].plain
    older = panels.attempt(VIEWS["busy"], theme, 60, 8, offset=3)[-1].plain
    far = panels.attempt(VIEWS["busy"], theme, 60, 8, offset=10_000)
    assert tail != older
    assert len(far) <= 8


def test_an_empty_run_says_so_instead_of_leaving_blanks() -> None:
    theme = THEMES["escuro"]
    assert "aguardando" in panels.attempt(VIEWS["empty"], theme, 60, 8)[-1].plain
    assert "nenhuma" in panels.rejections(VIEWS["empty"], theme, 60, 4)[0].plain


def test_hostile_text_cannot_carry_an_order_to_the_terminal() -> None:
    for text in every_panel(VIEWS["hostile"], THEMES["neon"], 80, 12, ("Entregue", HOSTILE)):
        assert not set(text.plain) & set("\x1b\x07‮\n\r\t")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0, "0"),
        (999, "999"),
        (1000, "1k"),
        (680_000, "680k"),
        (2_000_000, "2M"),
        (1_500_000, "1.5M"),
    ],
)
def test_counts_are_short(value: int, expected: str) -> None:
    assert panels.short_count(value) == expected


def test_the_states_have_words_and_unknown_ones_pass_through() -> None:
    assert panels.state_word("delivered") == "entregue"
    assert panels.state_word("something_new") == "something_new"
    assert width(panels.state_word("measuring_baseline")) > 0


def test_the_layout_follows_the_window() -> None:
    assert panels.layout_for(120, 36) == panels.Layout(compact=False, narrow=False)
    assert panels.layout_for(80, 24) == panels.Layout(compact=False, narrow=True)
    assert panels.layout_for(60, 16).compact
    assert panels.layout_for(120, 18).compact
    assert Role.TEXT in Role


def test_the_bar_shows_the_gates_by_name_then_by_number_then_by_symbol() -> None:
    theme = THEMES["escuro"]
    shown = busy()

    def bar(columns: int) -> str:
        return panels.gates_line(shown, theme, columns).plain

    names = bar(300)
    numbers = " ✓ 1 ✓ 2 ◔ 3 · 4 · 5 · 7 · 8 · 9 · 10 · 11"
    symbols = " ✓ ✓ ◔ · · · · · · ·"

    assert names.startswith(" ✓ escopo  ✓ segredos  ◔ lint  · build  · testes  · mutacao")
    assert names.endswith("· seguranca  · diferencial")
    assert bar(len(names)) == names
    assert bar(len(names) - 1) == numbers
    assert bar(len(numbers)) == numbers
    assert bar(len(numbers) - 1) == symbols


def test_the_details_show_the_task_its_checks_by_gate_and_its_rejections_whole() -> None:
    shown = view(task_id="t2", task_intent="reduzir parse_args (CCN 17)")
    lines = [line.plain for line in panels.details(shown, THEMES["escuro"], 40)]

    assert lines[0] == " tarefa t2 · tentativa 1/3"
    assert lines[1] == " reduzir parse_args (CCN 17)"
    assert " ✓ gate  1 · scope" in lines
    assert " ◔ gate  3 · lint" in lines
    assert " · gate  8 · complexity" in lines
    rejected = lines[lines.index(" rejeições desta tarefa") + 1 :]
    assert rejected[0].startswith(" ✗ t2-a1: format yyy")
    assert "".join(line.strip() for line in rejected[:-1]).count("y") == 200
    assert rejected[-1] == " ✗ t2-a2: lint"
    assert all(len(line) <= 40 for line in lines)


def test_the_details_leave_out_the_rejections_of_other_tasks() -> None:
    lines = [line.plain for line in panels.details(view(), THEMES["escuro"], 60)]

    assert lines[-2:] == [" rejeições desta tarefa", " nenhuma"]


def test_with_no_task_the_details_say_so() -> None:
    lines = panels.details(blank_view(), THEMES["escuro"], 60)

    assert [line.plain for line in lines] == [" nenhuma tarefa em andamento"]


@pytest.mark.parametrize(
    ("rows", "offset", "shown"),
    [
        (3, 0, ["c", "d", "e"]), (3, 1, ["b", "c", "d"]), (3, 2, ["a", "b", "c"]),
        (3, 99, ["a", "b", "c"]), (3, -1, ["c", "d", "e"]), (9, 0, list("abcde")),
        (0, 0, ["e"]), (1, 4, ["a"]), (9, 2, list("abcde")), (5, 1, list("abcde")),
    ],
)  # fmt: skip
def test_a_window_shows_the_rows_that_end_offset_lines_before_the_last(
    rows: int, offset: int, shown: list[str]
) -> None:
    lines = [Text(char) for char in "abcde"]

    assert [line.plain for line in panels.window(lines, rows, offset)] == shown


def test_the_log_has_every_line_whole_with_its_time() -> None:
    lines = [line.plain for line in panels.log_lines(view(), THEMES["escuro"], 50)]

    assert lines[0] == " 12:00:00 leu src/a0.py"
    assert lines[39] == " 12:00:39 leu src/a39.py"
    assert lines[40].startswith(" 12:01:00 falhou zzz")
    assert "".join(line.strip() for line in lines[41:]).count("z") == 150 - lines[40].count("z")
    assert all(line.startswith(" " * 10) for line in lines[41:])
    assert all(len(line) <= 50 for line in lines)


def test_an_empty_log_says_so() -> None:
    lines = panels.log_lines(blank_view(), THEMES["escuro"], 60)

    assert [line.plain for line in lines] == [" nenhuma atividade até agora"]


def test_with_ascii_symbols_the_details_and_the_log_cut_with_the_ascii_ellipsis() -> None:
    theme = with_ascii(THEMES["escuro"])
    for columns in range(10, 61):
        drawn = [
            *panels.details(view(task_id="t2"), theme, columns),
            *panels.log_lines(view(), theme, columns),
        ]
        for line in drawn:
            assert "…" not in line.plain and line.cell_len <= columns, (columns, line.plain)


def test_the_log_keeps_the_time_while_three_cells_are_left_for_the_text() -> None:
    def first(columns: int) -> str:
        return panels.log_lines(view(), THEMES["escuro"], columns)[0].plain

    assert first(13) == " 12:00:00 leu"
    assert first(12) == " leu"


def test_a_long_line_of_the_closing_report_is_wrapped_whole_and_not_cut() -> None:
    theme = THEMES["escuro"]
    long_line = (
        "Dependência nova: o uso (downloads) só é medido em npm e NuGet; em PyPI não é medido"
    )

    out = panels.final(["Entregue", long_line], view(state="delivered"), theme, 40, 20)

    shown = [text.plain for text in out]
    assert len(out) > 4
    assert all(theme.glyphs.marks.ellipsis not in line for line in shown[:-2])
    words = " ".join(" ".join(line.split()) for line in shown[1:-2]).split()
    assert words == long_line.split()


@pytest.mark.parametrize("rows", [1, 2, 3, 5])
def test_the_totals_line_stays_when_the_closing_report_does_not_fit(rows: int) -> None:
    theme = THEMES["escuro"]
    lines = [f"linha {n}" for n in range(10)]

    out = panels.final(lines, view(state="delivered"), theme, 60, rows)

    assert len(out) == rows
    assert "tarefa(s) integrada(s)" in out[-1].plain
    if rows > 2:
        assert "linha 0" in out[0].plain
        assert out[-2].plain.strip() == ""


def test_only_the_first_line_of_the_closing_report_carries_the_mark_and_the_bold() -> None:
    theme = THEMES["escuro"]
    out = panels.final(["Entregue " * 8, "segunda " * 8], view(state="delivered"), theme, 30, 20)

    marked = [text.plain for text in out if theme.glyphs.marks.passed in text.plain]
    assert len(marked) == 1
    assert out[0].plain.lstrip().startswith(theme.glyphs.marks.passed)
