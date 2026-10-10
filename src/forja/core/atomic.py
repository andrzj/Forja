import os
import sys
import time
import uuid
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path


def atomic_write_bytes(
    path: Path,
    data: bytes,
    *,
    fsync: Callable[[int], None] = os.fsync,
    replace: Callable[[Path, Path], None] = os.replace,
    sleep: Callable[[float], None] = time.sleep,
    attempts: int = 5,
    first_delay: float = 0.05,
) -> None:
    """Write ``data`` so that ``path`` holds either the old content or the new, never a mix.

    Temporary file, ``fsync``, then ``os.replace`` (atomic on NTFS within one volume). An
    antivirus or indexer holding the file shows up as ``PermissionError``; the replace is retried
    with a doubling delay. ``fsync`` and ``replace`` are injectable for fault-injection tests.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{uuid.uuid4().hex[:8]}.tmp")
    try:
        with temp.open("wb") as handle:
            handle.write(data)
            handle.flush()
            fsync(handle.fileno())
        delay = first_delay
        for attempt in range(1, attempts + 1):
            try:
                replace(temp, path)
                break
            except PermissionError:
                if attempt == attempts:
                    raise
                sleep(delay)
                delay *= 2
        _fsync_directory(path.parent, fsync)
    except BaseException:
        with suppress(OSError):
            temp.unlink()
        raise


def _fsync_directory(directory: Path, fsync: Callable[[int], None]) -> None:
    if sys.platform == "win32":
        return
    fd = os.open(directory, os.O_RDONLY)
    try:
        fsync(fd)
    finally:
        os.close(fd)
