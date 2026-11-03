"""The clones in a jscpd JSON report (``-r json``, file ``jscpd-report.json``).

jscpd marks a clone ``isNew`` when its content hash is missing from the baseline it was given; the
hash ignores paths and line numbers, so moving code does not make an old clone look new. Without a
baseline every clone is old.
"""

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CloneSide:
    path: str  # relative to the scanned directory, with forward slashes
    start: int  # first line
    end: int  # last line


@dataclass(frozen=True)
class Clone:
    first: CloneSide
    second: CloneSide
    lines: int
    tokens: int
    is_new: bool
    kind: str  # "exact", "renamed", "similar" or "semantic"
    format: str


def read_clones(report: Path) -> tuple[Clone, ...] | None:
    """The clones of a jscpd JSON report, ``None`` when it is not one."""
    try:
        document = json.loads(report.read_text(encoding="utf-8"))
        return tuple(_clone(entry) for entry in document["duplicates"])
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _clone(entry: dict[str, object]) -> Clone:
    return Clone(
        first=_side(entry["firstFile"]),
        second=_side(entry["secondFile"]),
        lines=_whole(entry["lines"]),
        tokens=_whole(entry["tokens"]),
        is_new=entry.get("isNew") is True,
        kind=str(entry.get("kind", "exact")),
        format=str(entry["format"]),
    )


def _side(raw: object) -> CloneSide:
    if not isinstance(raw, dict):
        raise TypeError("a clone side is not an object")
    path = str(raw["name"]).replace("\\", "/").removeprefix("./")
    return CloneSide(
        path=path, start=_line(raw, "start", "startLoc"), end=_line(raw, "end", "endLoc")
    )


def _line(raw: dict[str, object], plain: str, located: str) -> int:
    """A side's line: the ``line`` of ``startLoc``/``endLoc``, else ``start``/``end``."""
    place = raw.get(located)
    if isinstance(place, dict):
        return _whole(place["line"])
    return _whole(raw[plain])


def _whole(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError("not a whole number")
    return value
