"""What an attempt changed, read from git once and shared by every check."""

import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol

_OCTAL = re.compile(r"\\([0-7]{3})")
_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(?P<start>\d+)(?:,(?P<count>\d+))? @@")


class ChangeKind(StrEnum):
    ADDED = "A"
    MODIFIED = "M"
    DELETED = "D"
    RENAMED = "R"


@dataclass(frozen=True)
class Change:
    kind: ChangeKind
    path: str
    old_path: str | None = None  # only for a rename

    @property
    def before(self) -> str | None:
        """Where the content came from in the parent commit, if it existed there."""
        if self.kind is ChangeKind.ADDED:
            return None
        return self.old_path or self.path

    @property
    def exists_now(self) -> bool:
        return self.kind is not ChangeKind.DELETED


@dataclass(frozen=True)
class Changes:
    files: tuple[Change, ...]
    lines: int  # added plus removed, over all files
    patch: tuple[str, ...]  # the diff with no context, for scanners that read text
    ignored: tuple[str, ...] = ()  # files git ignores that are in the tree anyway

    def current(self, suffixes: tuple[str, ...] = ()) -> tuple[str, ...]:
        """Paths that exist after the change, optionally only those with one of the suffixes."""
        return tuple(
            c.path for c in self.files if c.exists_now and c.path.endswith(suffixes or ("",))
        )


class Git(Protocol):
    async def lines(self, *args: str) -> list[str]: ...


async def read_changes(git: Git, base: str = "HEAD") -> Changes:
    """Stage everything in the worktree and read what differs from its parent commit, or from
    ``base`` when the work is to be read against an earlier commit.

    Staging changes only the index of a disposable worktree and lets git see renames, which a
    plain status of untracked files cannot.
    """
    await git.lines("add", "-A")
    status = await git.lines("diff", "--cached", "--name-status", "-M", base)
    numstat = await git.lines("diff", "--cached", "--numstat", "-M", base)
    patch = await git.lines(
        "diff", "--cached", "-U0", "--no-color", base
    )  # git's defaults say the same
    ignored = await git.lines("ls-files", "--others", "--ignored", "--exclude-standard")
    return Changes(
        parse_status(status),
        count_lines(numstat),
        tuple(patch),
        tuple(unquote(path) for path in ignored),
    )


def unquote(name: str) -> str:
    """Undo git's quoting of unusual file names (``"caf\\303\\251.py"``)."""
    if not (len(name) >= 2 and name.startswith('"') and name.endswith('"')):
        return name
    body = name[1:-1]
    raw = bytearray()
    index = 0
    simple = {"n": 10, "t": 9, '"': 34, "\\": 92}
    while index < len(body):
        octal = _OCTAL.match(body, index)
        if octal:
            raw.append(int(octal[1], 8))
            index += 4
        elif body[index] == "\\" and index + 1 < len(body) and body[index + 1] in simple:
            raw.append(simple[body[index + 1]])
            index += 2
        else:
            raw += body[index].encode("utf-8")
            index += 1
    return raw.decode("utf-8", errors="replace")


def parse_status(lines: list[str]) -> tuple[Change, ...]:
    found = []
    for line in lines:
        fields = line.split("\t")
        code = fields[0][:1]
        if code == "R" and len(fields) == 3:
            found.append(Change(ChangeKind.RENAMED, unquote(fields[2]), unquote(fields[1])))
        elif code in ("A", "M", "D") and len(fields) == 2:
            found.append(Change(ChangeKind(code), unquote(fields[1])))
        elif code == "C" and len(fields) == 3:  # a copy is a new file as far as checks care
            found.append(Change(ChangeKind.ADDED, unquote(fields[2])))
        elif code == "T" and len(fields) == 2:  # a type change (file to symlink) is a change
            found.append(Change(ChangeKind.MODIFIED, unquote(fields[1])))
    return tuple(found)


def count_lines(numstat: list[str]) -> int:
    total = 0
    for line in numstat:
        added, _, rest = line.partition("\t")
        removed = rest.partition("\t")[0]
        total += (int(added) if added.isdigit() else 0) + (int(removed) if removed.isdigit() else 0)
    return total


@dataclass(frozen=True)
class AddedLine:
    path: str | None
    number: int | None  # the line's number in the new file
    text: str


def added_lines(patch: tuple[str, ...]) -> list[AddedLine]:
    """The lines a patch adds, each with the file and line it lands on.

    A header is only a header outside a hunk. Inside one, the count in its ``@@`` line says how
    many added lines belong to it, and a line that looks like ``+++ b/x`` is just an added line.
    """
    found: list[AddedLine] = []
    path: str | None = None
    new_line = owed = 0  # set by the first hunk before it is read
    for line in patch:
        if owed:
            if line.startswith("+"):
                found.append(AddedLine(path, new_line, line[1:]))
                new_line += 1
                owed -= 1
        elif line.startswith("+++ "):
            target = unquote(line[4:])
            path = target.removeprefix("b/") if target != "/dev/null" else None
        elif line.startswith("@@"):
            hunk = _HUNK.match(line)
            if hunk:
                new_line = int(hunk["start"])
                owed = int(hunk["count"]) if hunk["count"] is not None else 1
    return found


async def read_before(
    git: Git, changes: Changes, suffixes: tuple[str, ...], base: str = "HEAD"
) -> dict[str, str]:
    """The parent commit's (or ``base``'s) text of every changed file that had one, by old path."""
    contents = {}
    for change in changes.files:
        before = change.before
        if before is not None and before.endswith(suffixes):
            text = "\n".join(await git.lines("show", f"{base}:{before}"))
            contents[before] = text + "\n"
    return contents


def write_files(contents: dict[str, str], destination: Path) -> None:
    """Write texts under ``destination`` at their relative paths."""
    for relative, text in contents.items():
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8", newline="\n")
