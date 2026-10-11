"""Colors and style of the interface, as themes made of roles.

The screen never names a color: it asks for a role (``TEXT``, ``SUCCESS``, ``TOKENS``...) and the
theme answers. A theme is therefore a table, and a new one cannot leave a part of the screen
unpainted: every theme must define every role, and a test holds each one to the contrast the
reading needs (4.5 to 1 for text). Where the terminal has fewer colors the theme has its own map
of the 16 ANSI colors, not an automatic conversion, and with no color at all the screen still
says everything through symbols, bold and underline.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from rich.style import Style

from forja.ui.glyphs import ASCII, DOUBLE, ROUNDED, SINGLE, GlyphSet

ColorDepth = Literal["truecolor", "256", "16", "none"]
Titles = Literal["plain", "spaced", "tab"]


class Role(StrEnum):
    BACKGROUND = "background"
    SURFACE = "surface"  # bars and panels
    SURFACE_TEXT = "surface_text"
    BORDER = "border"
    TEXT = "text"
    MUTED = "muted"
    ACCENT = "accent"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"
    INFO = "info"
    SELECTION = "selection"
    SELECTION_TEXT = "selection_text"
    BAR = "bar"  # the status bar
    BAR_TEXT = "bar_text"
    TASKS = "tasks"  # the colors of the panels, for themes that paint a border by subject
    TOKENS = "tokens"
    GATES = "gates"
    ACTIVITY = "activity"
    REJECTED = "rejected"


# the pairs that must be readable, and by how much (WCAG contrast)
READABLE_ON_BACKGROUND = (
    Role.TEXT, Role.MUTED, Role.ACCENT, Role.SUCCESS, Role.WARNING, Role.ERROR, Role.INFO,
    Role.TASKS, Role.TOKENS, Role.GATES, Role.ACTIVITY, Role.REJECTED,
)  # fmt: skip
READABLE_PAIRS = (
    (Role.SURFACE_TEXT, Role.SURFACE),
    (Role.SELECTION_TEXT, Role.SELECTION),
    (Role.BAR_TEXT, Role.BAR),
)
MIN_CONTRAST = 4.5


@dataclass(frozen=True)
class Theme:
    key: str
    name: str
    kind: Literal["dark", "light"]
    colors: dict[Role, str]
    ansi: dict[Role, str]  # Rich color names for a terminal of 16 colors
    glyphs: GlyphSet
    titles: Titles = "plain"
    border_by_subject: bool = False  # each panel's border takes the color of what it shows
    shadow: bool = False

    def __post_init__(self) -> None:
        missing = [role.value for role in Role if role not in self.colors or role not in self.ansi]
        if missing:
            raise ValueError(f"theme {self.key} does not define {', '.join(missing)}")

    def color(self, role: Role, depth: ColorDepth) -> str | None:
        if depth == "none":
            return None
        return self.ansi[role] if depth == "16" else self.colors[role]

    def style(
        self,
        foreground: Role | None = None,
        background: Role | None = None,
        *,
        depth: ColorDepth = "truecolor",
        bold: bool = False,
        underline: bool = False,
        reverse: bool = False,
    ) -> Style:
        return Style(
            color=self.color(foreground, depth) if foreground else None,
            bgcolor=self.color(background, depth) if background else None,
            bold=bold or None,
            underline=underline or None,
            reverse=reverse or None,
        )


def _luminance(color: str) -> float:
    def channel(value: int) -> float:
        scaled = value / 255
        return scaled / 12.92 if scaled <= 0.03928 else ((scaled + 0.055) / 1.055) ** 2.4

    red, green, blue = (int(color[i : i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * channel(red) + 0.7152 * channel(green) + 0.0722 * channel(blue)


def contrast(foreground: str, background: str) -> float:
    """The WCAG contrast ratio of two ``#RRGGBB`` colors: 1 is none, 21 is black on white."""
    lighter, darker = sorted((_luminance(foreground), _luminance(background)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def _ansi(dark: bool, **overrides: str) -> dict[Role, str]:
    base = {
        Role.BACKGROUND: "black" if dark else "white",
        Role.SURFACE: "bright_black" if dark else "white",
        Role.SURFACE_TEXT: "white" if dark else "black",
        Role.BORDER: "bright_black" if dark else "bright_black",
        Role.TEXT: "white" if dark else "black",
        Role.MUTED: "bright_black",
        Role.ACCENT: "bright_blue" if dark else "blue",
        Role.SUCCESS: "bright_green" if dark else "green",
        Role.WARNING: "bright_yellow" if dark else "yellow",
        Role.ERROR: "bright_red" if dark else "red",
        Role.INFO: "bright_cyan" if dark else "blue",
        Role.SELECTION: "blue",
        Role.SELECTION_TEXT: "bright_white",
        Role.BAR: "blue",
        Role.BAR_TEXT: "bright_white",
        Role.TASKS: "bright_blue" if dark else "blue",
        Role.TOKENS: "bright_blue" if dark else "blue",
        Role.GATES: "bright_blue" if dark else "blue",
        Role.ACTIVITY: "bright_blue" if dark else "blue",
        Role.REJECTED: "bright_blue" if dark else "blue",
    }
    return {role: overrides.get(role.value, color) for role, color in base.items()}


def _colors(**values: str) -> dict[Role, str]:
    return {Role(name): color for name, color in values.items()}


def _same_subjects(color: str) -> dict[str, str]:
    return {"tasks": color, "tokens": color, "gates": color, "activity": color, "rejected": color}


ESCURO = Theme(
    "escuro",
    "Forja Escuro",
    "dark",
    _colors(
        background="#1E1E1E", surface="#252526", surface_text="#D4D4D4", border="#3C3C3C",
        text="#D4D4D4", muted="#858585", accent="#569CD6", success="#89D185", warning="#CCA700",
        error="#F14C4C", info="#3794FF", selection="#264F78", selection_text="#FFFFFF",
        bar="#007ACC", bar_text="#FFFFFF", **_same_subjects("#569CD6"),
    ),
    _ansi(True),
    ROUNDED,
)  # fmt: skip

DARCULA = Theme(
    "darcula",
    "Forja Darcula",
    "dark",
    _colors(
        background="#2B2B2B", surface="#3C3F41", surface_text="#A9B7C6", border="#515151",
        text="#A9B7C6", muted="#969696", accent="#7AA6D6", success="#8DB36E", warning="#FFC66D",
        error="#FF6B68", info="#589DF6", selection="#214283", selection_text="#FFFFFF",
        bar="#3C3F41", bar_text="#A9B7C6", **_same_subjects("#7AA6D6"),
    ),
    _ansi(True, warning="yellow", accent="bright_cyan"),
    ROUNDED,
)  # fmt: skip

CLARO = Theme(
    "claro",
    "Forja Claro",
    "light",
    _colors(
        background="#FFFFFF", surface="#F8F8F8", surface_text="#3B3B3B", border="#E5E5E5",
        text="#3B3B3B", muted="#6E7681", accent="#005FB8", success="#067D17", warning="#8A6100",
        error="#E51400", info="#0451A5", selection="#ADD6FF", selection_text="#1F1F1F",
        bar="#005FB8", bar_text="#FFFFFF", **_same_subjects("#005FB8"),
    ),
    _ansi(False),
    ROUNDED,
)  # fmt: skip

CONTRASTE = Theme(
    "contraste",
    "Alto contraste",
    "dark",
    _colors(
        background="#000000", surface="#000000", surface_text="#FFFFFF", border="#6FC3DF",
        text="#FFFFFF", muted="#BFBFBF", accent="#6FC3DF", success="#3FFF3F", warning="#FFFF00",
        error="#FF5555", info="#6FC3DF", selection="#FFFFFF", selection_text="#000000",
        bar="#6FC3DF", bar_text="#000000", **_same_subjects("#6FC3DF"),
    ),
    _ansi(True, selection="bright_white", selection_text="black", bar="bright_cyan",
          bar_text="black", border="bright_cyan"),
    SINGLE,
)  # fmt: skip

NEON = Theme(
    "neon",
    "Forja Neon",
    "dark",
    _colors(
        background="#0B0B0B", surface="#121212", surface_text="#D0D0D0", border="#2A2A2A",
        text="#D0D0D0", muted="#7A7A7A", accent="#00E5FF", success="#2BE04A", warning="#FF9F1A",
        error="#FF3B3B", info="#2D8CFF", selection="#1B5E20", selection_text="#7CFF8F",
        bar="#00263D", bar_text="#00E5FF", tasks="#00E5FF", tokens="#D84BFF", gates="#2BE04A",
        activity="#2D8CFF", rejected="#FF3B3B",
    ),
    _ansi(True, accent="bright_cyan", tasks="bright_cyan", tokens="bright_magenta",
          gates="bright_green", activity="bright_blue", rejected="bright_red", selection="green",
          selection_text="bright_green", bar="black", bar_text="bright_cyan"),
    SINGLE,
    titles="spaced",
    border_by_subject=True,
)  # fmt: skip

DOS = Theme(
    "dos",
    "Forja DOS",
    "dark",
    _colors(
        background="#0000AA", surface="#AAAAAA", surface_text="#000000", border="#AAAAAA",
        text="#AAAAAA", muted="#9C9CE0", accent="#55FFFF", success="#55FF55", warning="#FFFF55",
        error="#FF7070", info="#55FFFF", selection="#000000", selection_text="#FFFFFF",
        bar="#00AAAA", bar_text="#000000", **_same_subjects("#55FFFF"),
    ),
    _ansi(True, background="blue", surface="white", surface_text="black", border="white",
          text="white", muted="bright_blue", accent="bright_cyan", success="bright_green",
          warning="bright_yellow", error="bright_red", info="bright_cyan", selection="black",
          selection_text="bright_white", bar="cyan", bar_text="black"),
    DOUBLE,
    titles="tab",
    shadow=True,
)  # fmt: skip

THEMES = {theme.key: theme for theme in (ESCURO, DARCULA, CLARO, CONTRASTE, NEON, DOS)}
ORDER = tuple(THEMES)


def theme_named(key: str | None, *, dark_background: bool | None = None) -> Theme:
    """The theme asked for; without a name, the one that suits the terminal's background."""
    if key:
        found = THEMES.get(key.casefold())
        if found is None:
            raise KeyError(f"unknown theme {key!r}; the themes are {', '.join(ORDER)}")
        return found
    return CLARO if dark_background is False else ESCURO


def next_theme(current: Theme) -> Theme:
    """The theme after this one, for the key that cycles through them."""
    return THEMES[ORDER[(ORDER.index(current.key) + 1) % len(ORDER)]]


def with_ascii(theme: Theme) -> Theme:
    """The same theme with plain ASCII symbols, for a terminal or font that gets them wrong."""
    from dataclasses import replace  # noqa: PLC0415

    return replace(theme, glyphs=ASCII)
