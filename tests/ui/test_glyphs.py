"""The closed list of symbols and the way text is shortened: nothing may take another width."""

import unicodedata

import pytest
from rich.cells import cell_len

from forja.ui import glyphs
from forja.ui.glyphs import ASCII, SETS, allowed, fit, fit_path, pad, width

SAMPLES = [
    "",
    "a",
    "src/forja/orchestrator/agent_runner.py",
    "reduzir a complexidade de calcular_frete",
    "violações F401 → corrigido ✓",
    "日本語のテキスト",
    "emoji 🔒 here",
    "a" * 200,
]


def test_every_symbol_the_interface_may_draw_is_one_cell_wide() -> None:
    for char in allowed():
        assert cell_len(char) == 1, f"{char!r} (U+{ord(char):04X}) is not one cell wide"


def test_no_symbol_is_wide_or_fullwidth_in_any_terminal() -> None:
    for char in allowed():
        assert unicodedata.east_asian_width(char) not in ("W", "F"), char


def test_there_is_no_emoji_in_the_list() -> None:
    for char in allowed():
        assert not 0x1F000 <= ord(char) <= 0x1FFFF, char


def test_the_ascii_set_is_made_of_printable_ascii_only() -> None:
    assert all(32 <= ord(char) < 127 for char in ASCII.symbols())


def test_every_style_has_a_complete_set_and_a_name() -> None:
    assert set(SETS) == {"rounded", "single", "double", "ascii"}
    for name, symbols in SETS.items():
        assert symbols.name == name
        assert len(symbols.frame.horizontal) == len(symbols.frame.vertical) == 1
        assert width(symbols.gauge.full) == width(symbols.gauge.empty) == 1


@pytest.mark.parametrize("text", SAMPLES)
@pytest.mark.parametrize("size", [0, 1, 2, 5, 10, 33, 80])
def test_a_shortened_text_never_takes_more_cells_than_it_was_given(text: str, size: int) -> None:
    assert width(fit(text, size)) <= size
    assert width(pad(text, size)) == size
    assert width(pad(text, size, align="right")) == size
    assert width(pad(text, size, align="center")) == size
    assert width(fit_path(text, size)) <= size


def test_a_text_that_fits_is_left_alone() -> None:
    assert fit("abc", 3) == "abc"
    assert fit("abc", 10) == "abc"


def test_a_long_text_ends_with_an_ellipsis_in_the_last_cell() -> None:
    assert fit("abcdefghij", 6) == "abcde…"
    assert fit("abcdefghij", 1) == "…"


def test_a_path_keeps_the_name_of_the_file_and_loses_the_middle() -> None:
    shown = fit_path("src/forja/orchestrator/agent_runner.py", 30)

    assert shown.endswith("/agent_runner.py")
    assert "…" in shown
    assert width(shown) <= 30
    assert shown.startswith("src/")


def test_a_path_too_long_even_for_its_name_loses_the_end_of_the_name() -> None:
    shown = fit_path("src/a_very_long_file_name_indeed.py", 12)

    assert width(shown) <= 12
    assert shown.endswith("…")


def test_a_path_that_fits_is_left_alone() -> None:
    assert fit_path("src/a.py", 20) == "src/a.py"
    assert fit_path("src\\a.py", 20) == "src\\a.py"


def test_wide_characters_count_as_two_cells() -> None:
    assert width("日本") == 4
    assert width(fit("日本語", 5)) <= 5


def test_the_module_names_what_it_exports() -> None:
    assert glyphs.PRINTABLE
    assert glyphs.LETTERS
