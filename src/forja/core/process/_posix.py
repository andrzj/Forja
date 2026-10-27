import sys

if sys.platform != "win32":
    import os
    import signal
    from contextlib import suppress
    from pathlib import Path
    from typing import Any

    class PosixGroup:
        """Own session and process group: ``killpg`` reaches the whole tree.

        Unlike the Windows Job Object, nothing kills the tree if the tool itself dies.
        """

        def __init__(self) -> None:
            self._pid: int | None = None

        def spawn_kwargs(self) -> dict[str, Any]:
            return {"start_new_session": True}

        def attach(self, pid: int) -> None:
            self._pid = pid

        def interrupt(self) -> None:
            self._signal(signal.SIGTERM)

        def kill(self) -> None:
            self._signal(signal.SIGKILL)

        def peak_memory(self) -> int | None:
            return None  # no per-run measure: RUSAGE_CHILDREN is the whole Forja process's

        def close(self) -> None:
            self._pid = None

        def _signal(self, number: signal.Signals) -> None:
            if self._pid is not None:
                with suppress(ProcessLookupError, PermissionError):
                    os.killpg(self._pid, number)

    def creation_token(pid: int) -> int | None:
        """Start time in clock ticks since boot (field 22 of /proc/<pid>/stat)."""
        try:
            stat = Path(f"/proc/{pid}/stat").read_text()
        except OSError:
            return None
        fields = stat.rsplit(")", 1)[1].split()
        if fields[0] == "Z":
            return None
        return int(fields[19])

    def running_process_names() -> set[str]:
        """Lower-case command names of every process, read from /proc."""
        names: set[str] = set()
        for comm in Path("/proc").glob("[0-9]*/comm"):
            try:
                names.add(comm.read_text().strip().lower())
            except OSError:
                continue  # the process ended while we were looking
        return names

    def kill_process(pid: int) -> None:
        with suppress(ProcessLookupError, PermissionError):
            os.kill(pid, signal.SIGKILL)
