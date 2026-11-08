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
    ]


@pytest.mark.parametrize("name", list(VIEWS))
@pytest.mark.parametrize("key", list(THEMES))
def test_no_line_is_wider_than_its_room_at_any_width(name: str, key: str) -> None:
    for theme in (THEMES[key], with_ascii(THEMES[key])):
        for columns in WIDTHS:
            for text in every_panel(VIEWS[name], theme, columns, 12, ("Entregue", HOSTILE)):
                assert text.cell_len <= columns, (name, key, columns, text.plain)


@pytest.mark.parametrize("name", [n for n in VIEWS if n != "hostile"])
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
    assert any("t30" in line.plain for line in shown)


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
