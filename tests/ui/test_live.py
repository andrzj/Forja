"""The live line: aligned at every width in every theme, and it drops by priority, not at random."""

import io

import pytest
from rich.console import Console

from forja.ui.glyphs import ASCII, ROUNDED
from forja.ui.live import (
    HINT,
    LiveRenderer,
    clock_text,
    gauge,
    gauge_role,
    percent_text,
    render_status,
)
from forja.ui.terminal import Capabilities
from forja.ui.theme import THEMES, Role, Theme, with_ascii
from forja.ui.view import FeedLine, GateStatus, View, blank_view

DEPTHS = ("truecolor", "256", "16", "none")
WIDTHS = [1, 5, 12, 20, 30, 40, 59, 60, 61, 79, 80, 99, 100, 119, 120, 139, 140, 200, 300]


def gates(**changes: GateStatus) -> tuple[tuple[str, GateStatus], ...]:
    base = {
        "scope": GateStatus.PASSED, "secrets": GateStatus.PASSED, "format": GateStatus.PASSED,
        "lint": GateStatus.RUNNING, "build": GateStatus.PENDING, "tests": GateStatus.PENDING,
        "complexity": GateStatus.PENDING, "mutation": GateStatus.PENDING,
        "crap": GateStatus.PENDING,
        "pass_through": GateStatus.PENDING,
        "module_depth": GateStatus.PENDING,
        "dependency_cycles": GateStatus.PENDING,
        "layer_rules": GateStatus.PENDING,
        "package_metrics": GateStatus.PENDING,
        "sast": GateStatus.PENDING,
        "dependency_audit": GateStatus.PENDING,
        "new_dependency": GateStatus.PENDING,
        "differential": GateStatus.PENDING,
    }  # fmt: skip
    return tuple({**base, **changes}.items())


def busy(**changes: object) -> View:
    base = dict(
        objective="refatorar", repo="meu-servico", branch="forja/r1", isolation="WSL isolado",
        state="executing", tasks_total=5, tasks_done=2, task_id="t3",
        task_intent="reduzir a complexidade de calcular_frete (CCN 31)", attempt=1, attempts_max=3,
        gates=gates(), feed=(FeedLine("12:31:07", "edit", "editou src/frete.py (+14 -32)"),),
        feed_total=1, tokens_used=430, tokens_limit=1000, elapsed=751.0,
    )  # fmt: skip
    return blank_view(**{**base, **changes})


VIEWS = {
    "empty": blank_view(),
    "busy": busy(),
    "over": busy(tokens_used=1500),
    "wide text": busy(
        task_intent="日本語のテキスト " * 12, feed=(FeedLine("12:31:07", "text", "🔒 " * 40),)
    ),
    "ascii only": busy(task_intent="x" * 400),
    "paused": busy(state="paused", message="interrupted"),
}  # fmt: skip


LAST = FeedLine("12:31:09", "text", "pensando")  # shown in the live area, never printed above


def plain(lines: list, depth: str = "none") -> str:  # type: ignore[type-arg]
    out = io.StringIO()
    console = Console(file=out, force_terminal=False, color_system=None, width=500)
    for line in lines:
        console.print(line)
    return out.getvalue()


@pytest.mark.parametrize("theme", THEMES.values(), ids=lambda theme: theme.key)
@pytest.mark.parametrize("depth", DEPTHS)
@pytest.mark.parametrize("columns", WIDTHS)
@pytest.mark.parametrize("name", VIEWS)
def test_no_line_is_ever_wider_than_the_window(
    theme: Theme, depth: str, columns: int, name: str
) -> None:
    lines = render_status(VIEWS[name], theme, columns, depth)  # type: ignore[arg-type]

    assert len(lines) == 3
    for line in lines:
        assert line.cell_len <= columns, f"{theme.key} {depth} {columns} {name}: {line.plain!r}"


@pytest.mark.parametrize("theme", THEMES.values(), ids=lambda theme: theme.key)
def test_every_character_drawn_is_in_the_closed_list(theme: Theme) -> None:
    from forja.ui.glyphs import allowed  # noqa: PLC0415

    drawn = "".join(line.plain for line in render_status(VIEWS["busy"], theme, 120))

    assert set(drawn) <= allowed()


def test_with_ascii_symbols_nothing_outside_ascii_is_drawn() -> None:
    drawn = "".join(
        line.plain for line in render_status(VIEWS["busy"], with_ascii(THEMES["neon"]), 120)
    )

    assert drawn.isascii()


def test_with_no_color_there_is_no_escape_code_at_all() -> None:
    theme = THEMES["neon"]

    assert "\x1b" not in plain(render_status(VIEWS["busy"], theme, 100, "none"))


def test_the_first_line_says_which_task_which_attempt_and_what_for() -> None:
    first = render_status(VIEWS["busy"], THEMES["escuro"], 120)[0].plain

    assert first.startswith("▶ tarefa 3/5 · tentativa 1/3 · reduzir a complexidade")


def test_before_any_task_the_first_line_says_the_state_of_the_run() -> None:
    first = render_status(
        VIEWS["paused"].__class__(**{**VIEWS["paused"].__dict__, "tasks_total": 0}),
        THEMES["escuro"],
        120,
    )[0].plain

    assert first == "▶ paused · interrupted"


def test_the_second_line_has_the_gates_the_tokens_and_the_time_when_there_is_room() -> None:
    second = render_status(VIEWS["busy"], THEMES["escuro"], 200)[1].plain

    assert "✓escopo ✓segredos ✓formato ◔lint ·build ·testes ·complex." in second
    assert "·crap ·pass. ·prof. ·ciclos ·camadas ·pacotes ·sast" in second
    assert "·auditoria ·dep.nova ·difer." in second
    assert "tokens ████░░░░░░ 43%" in second
    assert second.endswith("12:31")


def test_a_narrow_window_loses_the_time_first_then_the_gates_and_never_the_tokens() -> None:
    def second(columns: int) -> str:
        return render_status(VIEWS["busy"], THEMES["escuro"], columns)[1].plain

    full = second(200)
    no_time = second(len(full) - 1)
    no_gates = second(len("tokens ████░░░░░░ 43%") + 3)
    tiny = second(len("tokens ████░░░░░░ 43%"))

    assert "12:31" in full and "12:31" not in no_time and "✓escopo" in no_time
    assert "✓escopo" not in no_gates and "tokens" in no_gates
    assert tiny == "tokens ████░░░░░░ 43%"


def test_the_third_line_has_the_last_news_and_the_hint_to_stop() -> None:
    third = render_status(VIEWS["busy"], THEMES["escuro"], 80)[2].plain

    assert third.startswith("12:31:07 editou src/frete.py (+14 -32)")
    assert third.endswith(HINT)
    assert len(third) == 80


def test_in_a_window_too_narrow_for_both_the_news_wins_over_the_hint() -> None:
    third = render_status(VIEWS["busy"], THEMES["escuro"], 25)[2].plain

    assert HINT not in third
    assert third.startswith("12:31:07 editou")


def test_a_run_with_no_news_yet_still_has_a_third_line() -> None:
    third = render_status(blank_view(), THEMES["escuro"], 80)[2].plain

    assert third.strip() == HINT


def test_over_the_limit_the_hint_turns_red_and_bold() -> None:
    theme = THEMES["escuro"]
    hint = render_status(VIEWS["over"], theme, 80, "truecolor")[2].spans[-1]

    assert "bold" in str(hint.style)
    assert theme.colors[Role.ERROR].lower() in str(hint.style).lower()


def test_a_gauge_fills_in_proportion_and_never_overflows() -> None:
    assert gauge(0.43, 10, ROUNDED) == ("████", "░░░░░░")
    assert gauge(0.0, 4, ROUNDED) == ("", "░░░░")
    assert gauge(1.0, 4, ROUNDED) == ("████", "")
    assert gauge(2.5, 4, ROUNDED) == ("████", "")
    assert gauge(-1, 4, ROUNDED) == ("", "░░░░")
    assert gauge(0.5, 4, ASCII) == ("##", "..")


@pytest.mark.parametrize(
    ("fraction", "role"),
    [(0.0, Role.TOKENS), (0.69, Role.TOKENS), (0.7, Role.WARNING), (1.0, Role.WARNING),
     (1.01, Role.ERROR)],
)  # fmt: skip
def test_the_gauge_changes_color_at_seventy_percent_and_over_the_limit(
    fraction: float, role: Role
) -> None:
    assert gauge_role(fraction) is role


@pytest.mark.parametrize(
    ("seconds", "text"),
    [
        (0, "00:00"), (59.9, "00:59"), (751, "12:31"), (3600, "1:00:00"), (3725, "1:02:05"),
        (-5, "00:00"),
    ],
)  # fmt: skip
def test_the_clock_text(seconds: float, text: str) -> None:
    assert clock_text(seconds) == text


def test_percent_text_rounds() -> None:
    assert percent_text(0.434) == "43%"
    assert percent_text(0.435) in ("43%", "44%")
    assert percent_text(1.5) == "150%"


def caps(**changes: object) -> Capabilities:
    base: dict[str, object] = dict(
        interactive=True, colors="truecolor", unicode=True, columns=100, rows=30, program="xterm",
        dark_background=True, can_resize=False, reduced_motion=False,
    )  # fmt: skip
    return Capabilities(**{**base, **changes})  # type: ignore[arg-type]


def test_the_renderer_prints_news_once_and_keeps_the_lines_at_the_bottom() -> None:
    out = io.StringIO()
    renderer = LiveRenderer(THEMES["neon"], caps(), out=out)
    first = busy(
        feed=(FeedLine("12:31:07", "edit", "editou src/a.py (+1 -1)"), LAST), feed_total=2,
        rejections=("t1-a1: gate 4 (lint): 2 new",), rejections_total=1,
    )  # fmt: skip

    renderer.start(first)
    renderer.update(first)
    renderer.update(first)
    renderer.stop(first)

    text = out.getvalue()
    assert text.count("editou src/a.py (+1 -1)") == 1
    assert text.count("gate 4 (lint): 2 new") == 1
    assert "Forja" in text and "refatorar" in text and "meu-servico" in text
    assert "executing" in text


def test_the_renderer_prints_only_what_is_new_even_when_the_feed_has_rolled() -> None:
    out = io.StringIO()
    renderer = LiveRenderer(THEMES["escuro"], caps(), out=out)
    old = tuple(FeedLine("12:00:00", "edit", f"editou f{n}.py (+1 -0)") for n in range(3)) + (LAST,)
    renderer.start(busy(feed=old, feed_total=4))
    renderer.update(busy(feed=old, feed_total=4))
    rolled = old[1:] + (FeedLine("12:00:01", "edit", "editou g.py (+2 -0)"), LAST)

    renderer.update(busy(feed=rolled, feed_total=6))
    renderer.stop(busy(feed=rolled, feed_total=6))

    text = out.getvalue()
    assert text.count("editou g.py") == 1
    assert text.count("editou f0.py") == 1


@pytest.mark.parametrize("colors", DEPTHS)
def test_the_renderer_works_at_every_depth_of_color(colors: str) -> None:
    out = io.StringIO()
    renderer = LiveRenderer(THEMES["dos"], caps(colors=colors), out=out)
    view = busy()

    renderer.start(view)
    renderer.update(view)
    renderer.stop(view)

    assert "Forja" in out.getvalue()
