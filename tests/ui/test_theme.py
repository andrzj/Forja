"""Each theme defines every role, passes the contrast the reading needs, and degrades with care."""

import pytest
from rich.color import Color, ColorSystem

from forja.ui.glyphs import ASCII
from forja.ui.theme import (
    MIN_CONTRAST,
    ORDER,
    READABLE_ON_BACKGROUND,
    READABLE_PAIRS,
    THEMES,
    Role,
    Theme,
    contrast,
    next_theme,
    theme_named,
    with_ascii,
)


def test_contrast_of_the_extremes() -> None:
    assert contrast("#000000", "#FFFFFF") == pytest.approx(21.0)
    assert contrast("#777777", "#777777") == pytest.approx(1.0)
    assert contrast("#FFFFFF", "#000000") == contrast("#000000", "#FFFFFF")


def test_there_are_two_dark_themes_and_a_light_one_at_least() -> None:
    kinds = [theme.kind for theme in THEMES.values()]

    assert kinds.count("dark") >= 2
    assert kinds.count("light") >= 1
    assert ORDER == ("escuro", "darcula", "claro", "contraste", "neon", "dos")


@pytest.mark.parametrize("theme", THEMES.values(), ids=lambda theme: theme.key)
def test_every_theme_defines_every_role(theme: Theme) -> None:
    assert set(theme.colors) == set(Role) == set(theme.ansi)


@pytest.mark.parametrize("theme", THEMES.values(), ids=lambda theme: theme.key)
def test_text_and_signals_are_readable_on_the_background(theme: Theme) -> None:
    background = theme.colors[Role.BACKGROUND]
    for role in READABLE_ON_BACKGROUND:
        ratio = contrast(theme.colors[role], background)
        assert ratio >= MIN_CONTRAST, f"{theme.key}: {role.value} is {ratio:.2f}"


@pytest.mark.parametrize("theme", THEMES.values(), ids=lambda theme: theme.key)
def test_text_is_readable_on_bars_and_on_the_selection(theme: Theme) -> None:
    for text, behind in READABLE_PAIRS:
        ratio = contrast(theme.colors[text], theme.colors[behind])
        assert ratio >= MIN_CONTRAST, f"{theme.key}: {text.value} on {behind.value} is {ratio:.2f}"


@pytest.mark.parametrize("theme", THEMES.values(), ids=lambda theme: theme.key)
def test_every_color_is_a_valid_hex_and_degrades_to_256_colors(theme: Theme) -> None:
    for role, color in theme.colors.items():
        assert len(color) == 7
        assert color.startswith("#"), (theme.key, role)
        assert Color.parse(color).downgrade(ColorSystem.EIGHT_BIT) is not None


@pytest.mark.parametrize("theme", THEMES.values(), ids=lambda theme: theme.key)
def test_every_sixteen_color_name_is_one_rich_knows(theme: Theme) -> None:
    for role, name in theme.ansi.items():
        assert Color.parse(name).type.name == "STANDARD", (theme.key, role, name)


def test_a_theme_missing_a_role_is_refused() -> None:
    partial: dict[Role, str] = {role: "#000000" for role in Role if role is not Role.ERROR}
    with pytest.raises(ValueError, match="error"):
        Theme("x", "X", "dark", partial, {role: "white" for role in Role}, ASCII)


def test_the_color_asked_for_depends_on_the_depth_of_the_terminal() -> None:
    theme = THEMES["neon"]

    assert theme.color(Role.ACCENT, "truecolor") == "#00E5FF"
    assert theme.color(Role.ACCENT, "256") == "#00E5FF"
    assert theme.color(Role.ACCENT, "16") == "bright_cyan"
    assert theme.color(Role.ACCENT, "none") is None


def test_a_style_has_the_colors_and_the_marks_asked_for() -> None:
    style = THEMES["escuro"].style(Role.ERROR, Role.BACKGROUND, bold=True, underline=True)

    assert style.color is not None
    assert style.color.name == "#f14c4c"
    assert style.bgcolor is not None
    assert style.bold
    assert style.underline
    plain = THEMES["escuro"].style(Role.ERROR, depth="none", bold=True)
    assert plain.color is None
    assert plain.bold


def test_only_the_neon_theme_paints_borders_by_subject_and_only_dos_has_a_shadow() -> None:
    assert [t.key for t in THEMES.values() if t.border_by_subject] == ["neon"]
    assert [t.key for t in THEMES.values() if t.shadow] == ["dos"]
    assert THEMES["neon"].titles == "spaced"
    assert THEMES["dos"].titles == "tab"


def test_the_neon_subjects_have_each_their_own_color() -> None:
    colors = THEMES["neon"].colors
    roles = (Role.TASKS, Role.TOKENS, Role.GATES, Role.ACTIVITY, Role.REJECTED)

    assert len({colors[role] for role in roles}) == 5


def test_without_a_name_the_theme_follows_the_background_of_the_terminal() -> None:
    assert theme_named(None, dark_background=False).key == "claro"
    assert theme_named(None, dark_background=True).key == "escuro"
    assert theme_named(None).key == "escuro"
    assert theme_named("NEON").key == "neon"


def test_an_unknown_theme_says_which_exist() -> None:
    with pytest.raises(KeyError, match="escuro, darcula"):
        theme_named("rosa")


def test_the_theme_key_goes_round_through_all_of_them() -> None:
    seen, theme = [], THEMES["escuro"]
    for _ in ORDER:
        seen.append(theme.key)
        theme = next_theme(theme)

    assert seen == list(ORDER)
    assert theme.key == "escuro"


def test_ascii_keeps_the_colors_and_changes_the_symbols() -> None:
    plain = with_ascii(THEMES["neon"])

    assert plain.glyphs is ASCII
    assert plain.colors == THEMES["neon"].colors


def test_a_style_has_no_emphasis_unless_asked_and_each_emphasis_is_independent() -> None:
    theme = THEMES["escuro"]
    plain = theme.style(Role.TEXT)

    assert (plain.bold, plain.underline, plain.reverse) == (None, None, None)
    assert theme.style(Role.TEXT, bold=True).bold is True
    assert theme.style(Role.TEXT, underline=True).underline is True
    assert theme.style(Role.TEXT, reverse=True).reverse is True
    only = theme.style(Role.TEXT, bold=True)
    assert (only.underline, only.reverse) == (None, None)
    only = theme.style(Role.TEXT, underline=True)
    assert (only.bold, only.reverse) == (None, None)
    only = theme.style(Role.TEXT, reverse=True)
    assert (only.bold, only.underline) == (None, None)


def test_the_sixteen_colors_of_a_dark_theme_are_the_dark_ones_and_of_a_light_theme_the_light_ones() -> (
    None
):
    dark, light = THEMES["escuro"].ansi, THEMES["claro"].ansi

    assert (dark[Role.BACKGROUND], dark[Role.TEXT]) == ("black", "white")
    assert (light[Role.BACKGROUND], light[Role.TEXT]) == ("white", "black")
    assert dark[Role.ACCENT] == "bright_blue" and light[Role.ACCENT] == "blue"


def test_a_theme_can_name_its_own_sixteen_colors_where_the_standard_ones_do_not_suit() -> None:
    assert THEMES["dos"].ansi[Role.BACKGROUND] == "blue"
    assert THEMES["dos"].ansi[Role.TEXT] == "white"
