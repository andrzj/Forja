"""The symbols the interface may draw with, and the one way it shortens text.

A layout stays aligned only if every symbol takes the same number of cells in every terminal. So
the interface draws from a closed list of symbols that are one cell wide (no emoji, no symbols of
ambiguous width), and a test holds every string it can show to that list. ``ASCII`` is the way
out for a terminal or a font that gets even these wrong.
"""

from dataclasses import dataclass

from rich.cells import cell_len


@dataclass(frozen=True)
class Frame:
    """The characters of a box, corner by corner."""

    top_left: str
    top_right: str
    bottom_left: str
    bottom_right: str
    horizontal: str
    vertical: str


@dataclass(frozen=True)
class Gauge:
    full: str
    empty: str


@dataclass(frozen=True)
class Marks:
    passed: str
    failed: str
    running: str
    pending: str
    current: str
    arrow: str
    bullet: str
    ellipsis: str
    minus: str


@dataclass(frozen=True)
class GlyphSet:
    name: str
    frame: Frame
    gauge: Gauge
    marks: Marks
    shade: str  # the dotted filler of a scroll bar or a track
    isolated: str  # in front of the isolation level

    def symbols(self) -> frozenset[str]:
        every = (*vars(self.frame).values(), *vars(self.gauge).values(), *vars(self.marks).values())
        return frozenset("".join((*every, self.shade, self.isolated)))


UNICODE_MARKS = Marks("✓", "✗", "◔", "·", "▶", "→", "·", "…", "-")
ASCII_MARKS = Marks("[X]", "[!]", "[~]", "[ ]", ">", "->", "-", "...", "-")

ROUNDED = GlyphSet(
    "rounded",
    Frame("╭", "╮", "╰", "╯", "─", "│"),
    Gauge("█", "░"),
    UNICODE_MARKS,
    "░",
    "◆",
)
SINGLE = GlyphSet(
    "single",
    Frame("┌", "┐", "└", "┘", "─", "│"),
    Gauge("▮", "▯"),
    UNICODE_MARKS,
    "░",
    "◆",
)
DOUBLE = GlyphSet(
    "double",
    Frame("╔", "╗", "╚", "╝", "═", "║"),
    Gauge("█", "░"),
    ASCII_MARKS,
    "░",
    "#",
)
ASCII = GlyphSet(
    "ascii",
    Frame("+", "+", "+", "+", "-", "|"),
    Gauge("#", "."),
    ASCII_MARKS,
    ".",
    "#",
)

SETS = {glyphs.name: glyphs for glyphs in (ROUNDED, SINGLE, DOUBLE, ASCII)}

# What any text of the interface may be made of besides the symbols of a set: printable ASCII
# and the letters of Portuguese.
LETTERS = frozenset("áàâãäéèêëíìîïóòôõöúùûüçÁÀÂÃÉÊÍÓÔÕÚÇñ")
PRINTABLE = frozenset(chr(code) for code in range(32, 127)) | LETTERS


def allowed() -> frozenset[str]:
    """Every character the interface may put on the screen, in any style."""
    every = frozenset().union(*(glyphs.symbols() for glyphs in SETS.values()))
    return PRINTABLE | every


def width(text: str) -> int:
    """How many cells the text takes on the screen."""
    return cell_len(text)


def _head(text: str, cells: int) -> str:
    """The first characters of the text that fit in ``cells`` cells."""
    out = ""
    for char in text:
        if width(out + char) > cells:
            break
        out += char
    return out


def fit(text: str, size: int, *, ellipsis: str = "…") -> str:
    """The text shortened to at most ``size`` cells, with an ellipsis at the end."""
    if size <= 0:
        return ""
    if width(text) <= size:
        return text
    room = size - width(ellipsis)
    if room <= 0:
        return _head(ellipsis, size)
    return _head(text, room) + ellipsis


def fit_path(path: str, size: int, *, ellipsis: str = "…") -> str:
    """A path shortened in the middle: the end, which names the file, is what stays."""
    if width(path) <= size:
        return path
    name = path.replace("\\", "/").rsplit("/", 1)[-1]
    room = size - width(ellipsis) - 1 - width(name)
    if room < 0:
        return fit(name, size, ellipsis=ellipsis)
    return f"{_head(path, room)}{ellipsis}/{name}"


def pad(text: str, size: int, *, align: str = "left") -> str:
    """The text, shortened if it must be, then filled with spaces to exactly ``size`` cells."""
    shown = fit(text, size)
    gap = size - width(shown)
    if align == "right":
        return " " * gap + shown
    if align == "center":
        left = gap // 2
        return " " * left + shown + " " * (gap - left)
    return shown + " " * gap
