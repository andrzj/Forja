"""Keeping the machine awake while a run goes on, and letting it sleep again after.

On Windows a run asks the system not to suspend (``SetThreadExecutionState``, Especificação) and
gives that up when the run ends, on any exit. The request belongs to the thread that made it, so
enter and leave on the same thread. Elsewhere nothing is asked and nothing is claimed.
"""

import contextlib
import sys
from collections.abc import Iterator

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001


def _set_state(flags: int) -> int:
    """The previous state, or 0 when the system refused."""
    import ctypes  # noqa: PLC0415
    from ctypes import wintypes  # noqa: PLC0415

    function = ctypes.windll.kernel32.SetThreadExecutionState  # type: ignore[attr-defined,unused-ignore]
    function.argtypes = [wintypes.DWORD]
    function.restype = wintypes.DWORD
    return int(function(flags))


@contextlib.contextmanager
def keep_awake() -> Iterator[bool]:
    """Yield whether the system was asked to stay awake (and will be told it may sleep after)."""
    if sys.platform != "win32":
        yield False
        return
    asked = _set_state(ES_CONTINUOUS | ES_SYSTEM_REQUIRED) != 0
    try:
        yield asked
    finally:
        if asked:
            _set_state(ES_CONTINUOUS)
