"""What every report reader shares: one error type, safe XML, and turning a tool's paths into
repository-relative POSIX paths."""

import json
import os
import re
import xml.etree.ElementTree as ET
from collections.abc import Sequence
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

# A report is a file somebody else wrote. These bound what reading one can cost.
MAX_REPORT_CHARS = 64 * 1024 * 1024
MAX_LINE = 10_000_000  # no source file has more lines than this


class ReportError(ValueError):
    """The report is not what its format says. The gate that needed it is inconclusive."""


def load_json(text: str) -> Any:
    try:
        return json.loads(text)
    except ValueError as error:
        raise ReportError(f"not valid JSON: {error}") from None


def load_xml(text: str) -> ET.Element:
    """Parse a report. Entity declarations are refused: the standard parser would expand them
    (a few lines of text can become gigabytes), and no coverage or mutation tool writes any.
    A DOCTYPE that only names a DTD (JaCoCo does) is harmless: the parser never fetches it."""
    if re.search(r"<!ENTITY", text, re.IGNORECASE):
        raise ReportError("the XML declares entities, which no report needs")
    try:
        return ET.fromstring(text)
    except ET.ParseError as error:
        raise ReportError(f"not valid XML: {error}") from None


def number(value: object, what: str) -> int:
    """A whole number from a report, whatever the tool used to write it (int or digits)."""
    if isinstance(value, bool):
        raise ReportError(f"{what} is not a number")
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value)
    raise ReportError(f"{what} is not a number: {value!r}")


def _inside(rest: str, root: Path) -> str | None:
    """``rest`` (an absolute path without its drive) made relative to ``root``, by comparing
    names only: the file system is never asked about a path a report supplied."""
    base = root.resolve().as_posix()
    base_parts = PurePosixPath(base[len(PureWindowsPath(base).drive) :]).parts
    given = PurePosixPath(rest).parts
    fold = str.casefold if os.name == "nt" else str
    if len(given) <= len(base_parts) or [fold(p) for p in given[: len(base_parts)]] != [
        fold(p) for p in base_parts
    ]:
        return None
    tail = given[len(base_parts) :]
    return "/".join(tail) if ".." not in tail else None


def resolve_path(raw: str, root: Path, source_roots: Sequence[str] = ()) -> str:
    """The repository-relative POSIX path of a file a tool named.

    Tools write absolute paths, paths relative to a source root (JaCoCo: package plus file name)
    or module paths (Go). The first reading that names a file that exists under ``root`` wins; a
    file that exists nowhere keeps its plainest reading, so the mismatch shows up as a file the
    repository does not have rather than as a lost one.

    The report is not trusted: network and device paths (UNC shares, device prefixes) are
    refused, absolute paths are compared by name and never opened, and ``..`` is an error.
    """
    text = raw.strip().replace("\\", "/")
    if not text:
        raise ReportError("an empty file path")
    if text.startswith("//"):
        raise ReportError(f"a network or device path in a report: {raw!r}")
    drive = PureWindowsPath(text).drive
    if drive or text.startswith("/"):
        text = text[len(drive) :]
        inside = _inside(text, root)
        if inside is not None:
            return inside
    parts = tuple(part for part in PurePosixPath(text).parts if part not in ("/", "."))
    if not parts or ".." in parts or any(":" in part for part in parts):
        raise ReportError(f"a file path that leaves the repository: {raw!r}")
    # drop leading components until what is left is a file under the root (Go module paths, a
    # source root the tool left out); try each source root first
    for start in range(len(parts)):
        tail = "/".join(parts[start:])
        for prefix in (*source_roots, ""):
            candidate = f"{prefix.strip('/')}/{tail}" if prefix.strip("/") else tail
            if (root / candidate).is_file():
                return candidate
    return "/".join(parts)
