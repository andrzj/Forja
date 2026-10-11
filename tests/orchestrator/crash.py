"""Ways for a run to die at a chosen place: a failing write, half a line, a frozen process."""

import os
import time
from collections.abc import Callable
from pathlib import Path

STALL_ENV = "ORCH_STALL"
TORN_ENV = "ORCH_TORN_AT"
PAUSE_ENV = "ORCH_AGENT_PAUSE"
STALLED_MARKER = "stalled"


class Interrupted(Exception):
    """Stands for the process dying at this point."""


class CrashAfter:
    """A ``write`` that lets ``writes`` lines through, then fails, maybe leaving half a line."""

    def __init__(self, writes: int, *, torn: bool = False) -> None:
        self.writes = writes
        self.torn = torn
        self.count = 0

    def __call__(self, fd: int, data: bytes) -> int:
        self.count += 1
        if self.count > self.writes:
            if self.torn:
                os.write(fd, data[: len(data) // 2])
            raise Interrupted(f"after {self.writes} lines")
        return os.write(fd, data)


class Counting:
    def __init__(self) -> None:
        self.count = 0

    def __call__(self, fd: int, data: bytes) -> int:
        self.count += 1
        return os.write(fd, data)


def stall_from_environment(root: Path) -> Callable[[str], None]:
    """Freeze at the point named in ``ORCH_STALL`` so a test can kill this process there."""
    wanted = os.environ.get(STALL_ENV)

    def stall(point: str) -> None:
        if point == wanted:
            (root / STALLED_MARKER).write_text(point)
            time.sleep(120)

    return stall


def torn_write_from_environment(root: Path) -> Callable[[int, bytes], int]:
    """Write half of the Nth line named in ``ORCH_TORN_AT`` and freeze, as a power cut would."""
    at = int(os.environ.get(TORN_ENV, "0"))
    count = 0

    def write(fd: int, data: bytes) -> int:
        nonlocal count
        count += 1
        if at and count == at:
            os.write(fd, data[: len(data) // 2])
            (root / STALLED_MARKER).write_text(f"write {at}")
            time.sleep(120)
        return os.write(fd, data)

    return write
