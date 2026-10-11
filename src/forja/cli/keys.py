"""Reading single keys while the run goes on, without waiting for Enter.

The keys the person can use during a run are few: ``ctrl+k`` stops it (and ``ctrl+c`` does the
same), ``t`` changes the theme. Reading is done in a thread, because a terminal has no portable
non-blocking read, and handed to the event loop as a queue. Tests give ``execute`` a scripted
source instead, so no terminal is needed to prove how stopping behaves.
"""

import asyncio
import contextlib
import sys
import threading
from collections.abc import AsyncIterator, Callable
from typing import Any, Protocol

KEYS = {"\x0b": "ctrl+k", "\x03": "ctrl+c", "t": "t", "T": "t"}


class KeySource(Protocol):
    def keys(self) -> AsyncIterator[str]: ...

    def close(self) -> None: ...


class TerminalKeys:
    """The keys of the terminal, read by a thread until ``close``."""

    def __init__(self) -> None:
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._restore: Callable[[], None] = lambda: None

    def start(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._thread = threading.Thread(target=self._read, daemon=True, name="forja-keys")
        self._thread.start()

    def _put(self, char: str) -> None:
        name = KEYS.get(char)
        if name is not None and self._loop is not None:
            self._loop.call_soon_threadsafe(self._queue.put_nowait, name)

    def _read(self) -> None:
        if sys.platform == "win32":
            self._read_windows()
        else:
            self._read_posix()

    def _read_windows(self) -> None:
        import msvcrt  # noqa: PLC0415

        while not self._stop.is_set():
            if msvcrt.kbhit():  # type: ignore[attr-defined,unused-ignore]
                self._put(msvcrt.getwch())  # type: ignore[attr-defined,unused-ignore]
            else:
                self._stop.wait(0.05)

    def _read_posix(self) -> None:
        import select  # noqa: PLC0415
        import termios  # noqa: PLC0415
        import tty  # noqa: PLC0415

        term: Any = termios  # the module only has these names on POSIX
        raw: Any = tty
        fd = sys.stdin.fileno()
        saved = term.tcgetattr(fd)
        self._restore = lambda: term.tcsetattr(fd, term.TCSADRAIN, saved)
        try:
            raw.setcbreak(fd)
            while not self._stop.is_set():
                if select.select([fd], [], [], 0.05)[0]:
                    self._put(sys.stdin.read(1))
        finally:
            self._restore()

    async def keys(self) -> AsyncIterator[str]:
        while True:
            yield await self._queue.get()

    def close(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1)
        with contextlib.suppress(Exception):
            self._restore()


def terminal_keys() -> TerminalKeys | None:
    """The keys of this terminal, or ``None`` when input is not a terminal (a pipe, CI)."""
    if not (sys.stdin and sys.stdin.isatty()):
        return None
    keys = TerminalKeys()
    keys.start()
    return keys
