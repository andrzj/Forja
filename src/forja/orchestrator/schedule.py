"""Which tasks may start now: the ones whose scopes touch neither a running task nor an earlier
task that is still open, and whose dependencies are integrated.

Pure: it reads the tasks in the order of the log and the states they are in, and decides. With a
limit of one it answers the first task that can start, which is what the run did before there was a
limit; the dependencies are read only above one, where the order of the log no longer says enough.
"""

from collections.abc import Collection, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class Candidate:
    task_id: str
    scope: tuple[str, ...]
    depends_on: tuple[str, ...] = ()


def _normal(path: str) -> str:
    """The path as a file system that ignores case, and dots and spaces at the end of a name, reads
    it (the spelling ``checks.scope`` compares by)."""
    parts = (part.rstrip(" .").casefold() for part in path.replace("\\", "/").split("/"))
    return "/".join(part for part in parts if part)


def _touch(one: str, other: str) -> bool:
    return one == other or one.startswith(other + "/") or other.startswith(one + "/")


def disjoint(first: Sequence[str], second: Sequence[str]) -> bool:
    """No entry of one scope is an entry of the other, or lies under a directory entry of it."""
    entries = [_normal(entry) for entry in second]
    return not any(_touch(_normal(entry), other) for entry in first for other in entries)


def startable(
    tasks: Sequence[Candidate],
    running: Collection[str],
    integrated: Collection[str],
    closed: Collection[str],
    limit: int,
) -> list[str]:
    """The ids, in the order of ``tasks``, that may start now without passing ``limit`` running.

    ``running`` are the tasks in progress; ``integrated`` those that joined the run; ``closed``
    those that will not run again (integrated or blocked). Every other task is open: it either runs
    or waits, and a later task whose scope touches it waits too.
    """
    room = limit - len(running)
    chosen: list[str] = []
    holding: list[Candidate] = []  # the open tasks seen so far: running, chosen or waiting
    for task in tasks:
        if task.task_id in closed:
            continue
        if (
            room > 0
            and task.task_id not in running
            and _may_start(task, holding, integrated, limit)
        ):
            chosen.append(task.task_id)
            room -= 1
        holding.append(task)
    return chosen


def _may_start(
    task: Candidate, holding: Sequence[Candidate], integrated: Collection[str], limit: int
) -> bool:
    if limit == 1:
        return not holding  # sequential: only the first open task, as before
    if not all(parent in integrated for parent in task.depends_on):
        return False
    return all(disjoint(task.scope, other.scope) for other in holding)
