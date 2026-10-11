"""What the terminal can do, and which kind of screen that allows.

Detection reads the environment and the answers of the terminal; it never assumes. A terminal
that cannot be told is treated as the modest one: sixteen colors, no resizing. The kind of screen
(the full interface, the live line or plain text) is chosen from this, and the person can force
another.
"""

import os
import re
import shutil
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from forja.ui.theme import ColorDepth

MIN_COLUMNS = 60
MIN_ROWS = 16
RECOMMENDED = (120, 36)  # columns, rows


class Tier(StrEnum):
    FULL = "completa"
    LIVE = "linha"
    TEXT = "texto"


@dataclass(frozen=True)
class Capabilities:
    interactive: bool
    colors: ColorDepth
    unicode: bool
    columns: int
    rows: int
    program: str
    dark_background: bool | None
    can_resize: bool
    reduced_motion: bool


def program_of(env: Mapping[str, str], platform: str) -> str:
    if env.get("WT_SESSION"):
        return "windows_terminal"
    if env.get("TERM_PROGRAM") == "vscode":
        return "vscode"
    if env.get("TMUX") or env.get("STY"):
        return "multiplexer"
    if env.get("TERM_PROGRAM") == "mintty" or env.get("MSYSTEM"):
        return "mintty"
    if env.get("TERM_PROGRAM") == "iTerm.app":
        return "iterm"
    if env.get("TERM", "").startswith("xterm"):
        return "xterm"
    return "conhost" if platform == "win32" else "unknown"


def color_depth(
    env: Mapping[str, str], *, interactive: bool, platform: str, windows_build: int | None
) -> ColorDepth:
    if not interactive or env.get("NO_COLOR") or env.get("TERM") == "dumb":
        return "none"
    if env.get("COLORTERM", "").lower() in ("truecolor", "24bit"):
        return "truecolor"
    if env.get("WT_SESSION") or env.get("TERM_PROGRAM") in ("vscode", "iTerm.app"):
        return "truecolor"
    if platform == "win32" and not env.get("TERM"):
        return "truecolor" if (windows_build or 0) >= 15063 else "16"
    return "256" if "256color" in env.get("TERM", "") else "16"


def background_from_env(env: Mapping[str, str]) -> bool | None:
    """Whether the background is dark, from ``COLORFGBG`` (``15;0`` is light text on black)."""
    value = env.get("COLORFGBG", "")
    if not value:
        return None
    try:
        background = int(value.rsplit(";", 1)[-1])
    except ValueError:
        return None
    return background < 7 or background == 8


_OSC11 = re.compile(r"rgb:([0-9a-fA-F]{2,4})/([0-9a-fA-F]{2,4})/([0-9a-fA-F]{2,4})")


def parse_background_reply(reply: str) -> bool | None:
    """Whether the background is dark, from the terminal's answer to the OSC 11 question."""
    found = _OSC11.search(reply)
    if found is None:
        return None
    red, green, blue = (int(part, 16) / (16 ** len(part) - 1) for part in found.groups())
    return bool((0.2126 * red + 0.7152 * green + 0.0722 * blue) < 0.5)


def detect(
    env: Mapping[str, str] | None = None,
    *,
    interactive: bool | None = None,
    encoding: str | None = None,
    size: tuple[int, int] | None = None,
    platform: str | None = None,
    windows_build: int | None = None,
    asked_background: bool | None = None,
) -> Capabilities:
    env = os.environ if env is None else env
    platform = sys.platform if platform is None else platform
    if interactive is None:
        interactive = sys.stdout.isatty()
    encoding = encoding if encoding is not None else (sys.stdout.encoding or "")
    columns, rows = size if size is not None else tuple(shutil.get_terminal_size((80, 24)))
    program = program_of(env, platform)
    dark = asked_background if asked_background is not None else background_from_env(env)
    return Capabilities(
        interactive=interactive,
        colors=color_depth(
            env, interactive=interactive, platform=platform, windows_build=windows_build
        ),
        unicode="utf" in encoding.lower(),
        columns=columns,
        rows=rows,
        program=program,
        dark_background=dark,
        can_resize=interactive and program in ("xterm", "mintty", "iterm"),
        reduced_motion=bool(env.get("NO_MOTION") or env.get("REDUCE_MOTION")),
    )


def choose_tier(
    caps: Capabilities, forced: Tier | None = None, *, full_available: bool = False
) -> tuple[Tier, str | None]:
    """The kind of screen to draw, and the reason when it is not the best one asked for."""
    if forced is not None:
        if forced is not Tier.TEXT and not caps.interactive:
            return Tier.TEXT, "a saída não é um terminal"
        wanted = forced
    elif not caps.interactive:
        return Tier.TEXT, None
    else:
        wanted = Tier.FULL
    if wanted is Tier.FULL:
        if caps.columns < MIN_COLUMNS or caps.rows < MIN_ROWS:
            small = f"{caps.columns}x{caps.rows}"
            return (
                Tier.LIVE,
                f"a janela está pequena ({small}); a tela completa pede ao menos 60x16",
            )
        if not full_available:
            return Tier.LIVE, None
    return wanted, None


def resize_sequences(
    caps: Capabilities, wanted: tuple[int, int] = RECOMMENDED
) -> tuple[str, str] | None:
    """The sequence that enlarges the window and the one that puts it back, if both are safe.

    Only enlarging, only where the terminal takes the xterm sequence, never inside a multiplexer
    or an embedded terminal, and never when the window is already big enough.
    """
    if not caps.can_resize:
        return None
    columns, rows = max(wanted[0], caps.columns), max(wanted[1], caps.rows)
    if (columns, rows) == (caps.columns, caps.rows):
        return None
    return f"\x1b[8;{rows};{columns}t", f"\x1b[8;{caps.rows};{caps.columns}t"
