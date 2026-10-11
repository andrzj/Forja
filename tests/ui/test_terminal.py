"""Detecting the terminal and choosing the screen it allows."""

import pytest

from forja.ui.terminal import (
    Capabilities,
    Tier,
    background_from_env,
    choose_tier,
    color_depth,
    detect,
    parse_background_reply,
    program_of,
    resize_sequences,
)


def caps(**changes: object) -> Capabilities:
    base: dict[str, object] = {
        "interactive": True,
        "colors": "truecolor",
        "unicode": True,
        "columns": 120,
        "rows": 36,
        "program": "windows_terminal",
        "dark_background": True,
        "can_resize": False,
        "reduced_motion": False,
    }
    return Capabilities(**{**base, **changes})  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("env", "platform", "program"),
    [
        ({"WT_SESSION": "x"}, "win32", "windows_terminal"),
        ({"TERM_PROGRAM": "vscode"}, "win32", "vscode"),
        ({"TMUX": "/tmp/x"}, "linux", "multiplexer"),
        ({"TERM_PROGRAM": "mintty"}, "win32", "mintty"),
        ({"MSYSTEM": "MINGW64"}, "win32", "mintty"),
        ({"TERM_PROGRAM": "iTerm.app"}, "darwin", "iterm"),
        ({"TERM": "xterm-256color"}, "linux", "xterm"),
        ({}, "win32", "conhost"),
        ({}, "linux", "unknown"),
    ],
)
def test_the_program_is_told_from_the_environment(
    env: dict[str, str], platform: str, program: str
) -> None:
    assert program_of(env, platform) == program


@pytest.mark.parametrize(
    ("env", "interactive", "platform", "build", "depth"),
    [
        ({"COLORTERM": "truecolor"}, True, "linux", None, "truecolor"),
        ({"COLORTERM": "24bit"}, True, "linux", None, "truecolor"),
        ({"WT_SESSION": "x"}, True, "win32", None, "truecolor"),
        ({"TERM_PROGRAM": "vscode"}, True, "linux", None, "truecolor"),
        ({"TERM": "xterm-256color"}, True, "linux", None, "256"),
        ({"TERM": "xterm"}, True, "linux", None, "16"),
        ({"TERM": "dumb"}, True, "linux", None, "none"),
        ({"COLORTERM": "truecolor", "NO_COLOR": "1"}, True, "linux", None, "none"),
        ({"COLORTERM": "truecolor"}, False, "linux", None, "none"),
        ({}, True, "win32", 22631, "truecolor"),
        ({}, True, "win32", 10240, "16"),
        ({}, True, "win32", None, "16"),
        ({}, True, "linux", None, "16"),
    ],
)
def test_the_depth_of_color_comes_from_what_the_terminal_declares(
    env: dict[str, str], interactive: bool, platform: str, build: int | None, depth: str
) -> None:
    found = color_depth(env, interactive=interactive, platform=platform, windows_build=build)

    assert found == depth


def test_an_empty_no_color_does_not_switch_color_off() -> None:
    env = {"NO_COLOR": "", "COLORTERM": "truecolor"}

    assert color_depth(env, interactive=True, platform="linux", windows_build=None) == "truecolor"


@pytest.mark.parametrize(
    ("value", "dark"),
    [
        ("15;0", True),
        ("0;15", False),
        ("15;default;0", True),
        ("7;8", True),
        ("0;7", False),
        ("", None),
        ("x", None),
        ("15;x", None),
    ],
)
def test_the_background_from_colorfgbg(value: str, dark: bool | None) -> None:
    assert background_from_env({"COLORFGBG": value} if value else {}) is dark


@pytest.mark.parametrize(
    ("reply", "dark"),
    [
        ("\x1b]11;rgb:0000/0000/0000\x07", True),
        ("\x1b]11;rgb:ffff/ffff/ffff\x1b\\", False),
        ("\x1b]11;rgb:1e/1e/1e\x07", True),
        ("\x1b]11;rgb:fa/fa/fa\x07", False),
        ("nothing useful", None),
        ("", None),
    ],
)
def test_the_background_from_the_answer_of_the_terminal(reply: str, dark: bool | None) -> None:
    assert parse_background_reply(reply) is dark


def test_detection_puts_the_pieces_together() -> None:
    found = detect(
        {"WT_SESSION": "x", "COLORFGBG": "15;0"},
        interactive=True,
        encoding="utf-8",
        size=(150, 40),
        platform="win32",
    )

    assert found == caps(columns=150, rows=40)


def test_what_the_terminal_answered_wins_over_the_variable() -> None:
    found = detect(
        {"COLORFGBG": "15;0"},
        interactive=True,
        encoding="utf-8",
        size=(80, 24),
        platform="linux",
        asked_background=False,
    )

    assert found.dark_background is False


def test_a_terminal_that_is_not_utf_8_gets_no_unicode() -> None:
    found = detect({}, interactive=True, encoding="cp1252", size=(80, 24), platform="win32")

    assert not found.unicode


def test_only_xterm_like_terminals_outside_a_multiplexer_can_be_resized() -> None:
    def resizable(env: dict[str, str], interactive: bool = True) -> bool:
        found = detect(env, interactive=interactive, encoding="utf-8", size=(80, 24))
        return found.can_resize

    assert resizable({"TERM": "xterm-256color"})
    assert not resizable({"TERM": "xterm", "TMUX": "x"})
    assert not resizable({"TERM": "xterm"}, interactive=False)


def test_reduced_motion_is_asked_for_by_the_environment() -> None:
    found = detect({"NO_MOTION": "1"}, interactive=True, encoding="utf-8", size=(80, 24))

    assert found.reduced_motion


@pytest.mark.parametrize(
    ("changes", "forced", "available", "tier", "why"),
    [
        ({"interactive": False}, None, True, Tier.TEXT, None),
        ({}, None, False, Tier.LIVE, None),
        ({}, None, True, Tier.FULL, None),
        ({"columns": 59}, None, True, Tier.LIVE, "pequena (59x36)"),
        ({"rows": 15}, None, True, Tier.LIVE, "pequena (120x15)"),
        ({"columns": 60, "rows": 16}, None, True, Tier.FULL, None),
        ({}, Tier.TEXT, True, Tier.TEXT, None),
        ({}, Tier.LIVE, True, Tier.LIVE, None),
        ({"interactive": False}, Tier.FULL, True, Tier.TEXT, "não é um terminal"),
        ({"columns": 40}, Tier.FULL, True, Tier.LIVE, "pequena (40x36)"),
    ],
)
def test_the_screen_is_chosen_from_the_terminal_and_a_small_window_falls_back(
    changes: dict[str, object], forced: Tier | None, available: bool, tier: Tier, why: str | None
) -> None:
    chosen, reason = choose_tier(caps(**changes), forced, full_available=available)

    assert chosen is tier
    if why is None:
        assert reason is None
    else:
        assert reason is not None
        assert why in reason


def test_the_window_is_enlarged_only_where_it_is_safe_and_restored_after() -> None:
    small = caps(can_resize=True, columns=80, rows=24)

    assert resize_sequences(small) == ("\x1b[8;36;120t", "\x1b[8;24;80t")


@pytest.mark.parametrize(
    "changes",
    [
        {"can_resize": False, "columns": 80, "rows": 24},
        {"can_resize": True, "columns": 200, "rows": 60},
        {"can_resize": True, "columns": 120, "rows": 36},
    ],
)
def test_the_window_is_left_alone_when_it_cannot_or_need_not_change(
    changes: dict[str, object],
) -> None:
    assert resize_sequences(caps(**changes)) is None


def test_a_window_big_in_one_dimension_is_enlarged_only_in_the_other() -> None:
    wide = caps(can_resize=True, columns=200, rows=20)

    assert resize_sequences(wide) == ("\x1b[8;36;200t", "\x1b[8;20;200t")
