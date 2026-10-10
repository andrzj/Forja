import sys

from forja.core.process.model import ProcessIdentity


def creation_token(pid: int) -> int | None:
    """Creation time of a live process, or ``None`` if it does not exist or has exited."""
    if sys.platform == "win32":
        from forja.core.process import _windows

        return _windows.creation_token(pid)
    from forja.core.process import _posix

    return _posix.creation_token(pid)


def running_process_names() -> set[str]:
    """Lower-case names of all running processes (``git.exe`` on Windows, ``git`` on Linux)."""
    if sys.platform == "win32":
        from forja.core.process import _windows

        return _windows.running_process_names()
    from forja.core.process import _posix

    return _posix.running_process_names()


def kill_leftover(identity: ProcessIdentity) -> bool:
    """Kill the process only if the pid still belongs to the one that was recorded.

    The creation time guards against pid reuse: a different process under the same pid is left
    alone. Returns whether a process was killed. Descendants are not reached; the group's
    kill-on-close already covers them when the tool died.
    """
    if identity.creation_token is None or creation_token(identity.pid) != identity.creation_token:
        return False
    if sys.platform == "win32":
        from forja.core.process import _windows

        _windows.kill_process(identity.pid)
    else:
        from forja.core.process import _posix

        _posix.kill_process(identity.pid)
    return True
