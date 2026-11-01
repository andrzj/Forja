"""Peak memory of one process group on POSIX, by sampling.

No kernel counter covers one run's tree: ``RUSAGE_CHILDREN`` is the whole Forja process's and
holds only the largest single process. So the resident bytes of every process of the group are
summed at short intervals and the largest sum is the peak. Linux reads ``/proc``; macOS has no
``/proc`` and asks ``ps``. Nothing here needs POSIX to import, so the parsing is tested anywhere.
"""

import mmap
import subprocess
import sys
import threading
from collections.abc import Callable
from pathlib import Path

INTERVAL = 0.05

# (process group id, resident bytes) of every process alive at that moment.
Snapshot = Callable[[], list[tuple[int, int]]]


def parse_proc(stat: str, statm: str, page_size: int) -> tuple[int, int]:
    """Process group (field 5 of ``/proc/<pid>/stat``) and resident bytes (field 2 of ``statm``)."""
    group = int(stat.rsplit(")", 1)[1].split()[2])
    return group, int(statm.split()[1]) * page_size


def parse_ps(output: str) -> list[tuple[int, int]]:
    """Lines of ``ps -axo pgid=,rss=``: the group and the resident size in KiB."""
    found = []
    for line in output.splitlines():
        fields = line.split()
        if len(fields) == 2 and all(field.isdigit() for field in fields):
            found.append((int(fields[0]), int(fields[1]) * 1024))
    return found


def read_proc() -> list[tuple[int, int]]:
    found = []
    for entry in Path("/proc").glob("[0-9]*"):
        try:
            found.append(
                parse_proc(
                    (entry / "stat").read_text(), (entry / "statm").read_text(), mmap.PAGESIZE
                )
            )
        except (OSError, ValueError, IndexError):
            continue  # the process ended, or is not ours to read
    return found


def read_ps() -> list[tuple[int, int]]:
    try:
        done = subprocess.run(
            ["ps", "-axo", "pgid=,rss="], capture_output=True, text=True, check=False, timeout=5
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    return parse_ps(done.stdout)


def default_snapshot() -> Snapshot:
    return read_proc if sys.platform == "linux" else read_ps


class PeakSampler:
    """Sums the resident bytes of the processes in ``group`` until ``stop``."""

    def __init__(self, group: int, snapshot: Snapshot, interval: float = INTERVAL) -> None:
        self._group = group
        self._snapshot = snapshot
        self._interval = interval
        self._peak = 0
        self._stopped = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> int | None:
        """Peak bytes seen, or ``None`` when no process of the group was ever seen holding any."""
        self._stopped.set()
        if self._thread.is_alive():
            self._thread.join()
        return self._peak or None

    def _run(self) -> None:
        while True:
            held = sum(size for group, size in self._snapshot() if group == self._group)
            self._peak = max(self._peak, held)
            if self._stopped.wait(self._interval):
                return
