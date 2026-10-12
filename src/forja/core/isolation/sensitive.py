"""Which files count as sensitive, with a small gitignore-style glob matcher.

Sensitive files are never sent to a model and never exist in the agent's working copy. The
matcher is our own (no `pathspec` dependency) and understands only what is needed:
``*`` and ``?`` inside a path segment, ``**`` as a whole segment, a leading ``/`` to anchor.
A pattern without a slash matches at any depth; a pattern that matches a directory covers
everything under it.
"""

import re
import sys
from collections.abc import Iterable, Sequence

DEFAULT_SENSITIVE_PATTERNS: tuple[str, ...] = (
    ".env",
    ".env.*",
    "*.pem",
    "*.key",
    "*.pfx",
    "*.p12",
    "id_rsa*",
    "id_ed25519*",
    ".npmrc",
    ".pypirc",
    ".netrc",
    "credentials*",
    "secrets/**",
    ".aws/**",
    ".ssh/**",
)


def _segment_regex(segment: str) -> str:
    out = []
    for char in segment:
        if char == "*":
            out.append("[^/]*")
        elif char == "?":
            out.append("[^/]")
        else:
            out.append(re.escape(char))
    return "".join(out)


def _split_segments(pattern: str, text: str) -> list[str]:
    if not text or "\\" in text or text.startswith("!") or text.endswith("/"):
        raise ValueError(f"invalid sensitive-file pattern {pattern!r}")
    segments = text.lstrip("/").split("/")
    if any(s in ("", ".", "..") for s in segments):
        raise ValueError(f"invalid sensitive-file pattern {pattern!r}")
    if any("**" in s and s != "**" for s in segments):
        raise ValueError(f"'**' must be a whole path segment in {pattern!r}")
    return segments


def _piece_regex(segment: str, is_last: bool) -> str:
    if segment == "**":
        return ".+" if is_last else "(?:[^/]+/)*"
    return _segment_regex(segment) + ("" if is_last else "/")


def compile_pattern(pattern: str, *, case_insensitive: bool) -> re.Pattern[str]:
    """Translate one pattern; ``ValueError`` for anything that is not a plain relative glob."""
    text = pattern.strip()
    segments = _split_segments(pattern, text)
    anchored = text.startswith("/") or "/" in text
    last = len(segments) - 1
    pieces = [_piece_regex(segment, index == last) for index, segment in enumerate(segments)]
    prefix = "" if anchored else "(?:.*/)?"
    flags = re.IGNORECASE if case_insensitive else 0
    return re.compile(prefix + "".join(pieces), flags)


class SensitivePaths:
    """A set of patterns and the question "is this repository-relative path sensitive?"."""

    def __init__(
        self,
        patterns: Iterable[str] = DEFAULT_SENSITIVE_PATTERNS,
        *,
        case_insensitive: bool | None = None,
    ) -> None:
        self.patterns: tuple[str, ...] = tuple(dict.fromkeys(patterns))
        insensitive = sys.platform == "win32" if case_insensitive is None else case_insensitive
        self._compiled = [compile_pattern(p, case_insensitive=insensitive) for p in self.patterns]

    @classmethod
    def with_defaults(
        cls, extra: Iterable[str] = (), *, case_insensitive: bool | None = None
    ) -> "SensitivePaths":
        """The built-in patterns plus the ones a repository adds; the defaults cannot be removed."""
        return cls((*DEFAULT_SENSITIVE_PATTERNS, *extra), case_insensitive=case_insensitive)

    def matches(self, path: str) -> bool:
        """True if the path, or any directory above it, matches a pattern."""
        parts = path.replace("\\", "/").strip("/").split("/")
        prefixes = ["/".join(parts[: i + 1]) for i in range(len(parts))]
        return any(regex.fullmatch(prefix) for regex in self._compiled for prefix in prefixes)

    def split(self, paths: Sequence[str]) -> tuple[list[str], list[str]]:
        """Return ``(kept, excluded)``, each in the original order."""
        kept: list[str] = []
        excluded: list[str] = []
        for path in paths:
            (excluded if self.matches(path) else kept).append(path)
        return kept, excluded
