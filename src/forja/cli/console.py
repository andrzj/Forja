"""Talking to the person before the run: saying things and asking questions.

The run itself is shown by the renderers; this is only the preparation, where there are at most a
few questions. Whatever is typed or printed passes through ``clean`` like everything else.
"""

import sys
from collections.abc import Sequence
from typing import Protocol

from forja.ui.glyphs import clean


class Console(Protocol):
    interactive: bool

    def say(self, text: str = "") -> None: ...

    def ask(self, question: str, *, default: str = "") -> str: ...


def lenient_output() -> None:
    """A character the output encoding cannot hold is replaced, never an exception.

    Redirected to a file or a pipe, Windows gives the output the ANSI code page (cp1252), and an
    agent's text with an arrow or an emoji would stop the run in the middle of the write.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(errors="replace")


class TerminalConsole:
    def __init__(self) -> None:
        self.interactive = bool(sys.stdin and sys.stdin.isatty() and sys.stdout.isatty())

    def say(self, text: str = "") -> None:
        print(clean(text))

    def ask(self, question: str, *, default: str = "") -> str:
        if not self.interactive:
            return default
        try:
            answer = input(f"{clean(question)} ").strip()
        except EOFError:
            return default
        return answer or default


class Unattended:
    """A console that never asks: what is said reaches ``inner``, every question gets its default.

    ``--config`` runs on it, even on a terminal, so a CI run and the same file typed by hand agree.
    """

    interactive = False

    def __init__(self, inner: Console) -> None:
        self._inner = inner

    def say(self, text: str = "") -> None:
        self._inner.say(text)

    def ask(self, question: str, *, default: str = "") -> str:
        return default


def choose(console: Console, question: str, options: Sequence[str], *, default: int = 1) -> int:
    """Ask for one of the options by number; the index (from 0) of the chosen one."""
    console.say(question)
    for number, option in enumerate(options, start=1):
        console.say(f"  {number}. {option}")
    while True:
        answer = console.ask(f"Escolha [1-{len(options)}, padrão {default}]:", default=str(default))
        if answer.isdigit() and 1 <= int(answer) <= len(options):
            return int(answer) - 1
        if not console.interactive:
            return default - 1
        console.say("Responda com o número de uma das opções.")


def confirm(console: Console, question: str) -> bool:
    return console.ask(f"{question} [s/N]", default="n").lower() in ("s", "sim", "y", "yes")
