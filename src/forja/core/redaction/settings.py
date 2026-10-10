"""What a repository may change about redaction. Built-in secret detectors are never optional."""

import hashlib
import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from forja.core.events.models import canonical_json

MAX_ITEM_CHARS = 1_048_576
MAX_LINE_CHARS = 20_000
_NAME = re.compile(r"^[a-z][a-z0-9-]{0,40}$")


class PiiKind(StrEnum):
    CPF = "cpf"
    CNPJ = "cnpj"
    EMAIL = "email"
    PHONE = "phone"
    CARD = "card"


class RedactionSettingsError(ValueError):
    pass


def compile_extra(name: str, pattern: str) -> re.Pattern[str]:
    """Validate and compile a repository pattern; at most one capture group (the secret)."""
    if not _NAME.fullmatch(name):
        raise RedactionSettingsError(
            f"invalid pattern name {name!r}: use lower-case letters, digits, '-'"
        )
    try:
        compiled = re.compile(pattern)
    except re.error as error:
        raise RedactionSettingsError(
            f"pattern {name!r} is not a valid regular expression: {error}"
        ) from None
    if compiled.groups > 1:
        raise RedactionSettingsError(f"pattern {name!r} has more than one capture group")
    if compiled.match(""):
        raise RedactionSettingsError(f"pattern {name!r} matches the empty string")
    return compiled


@dataclass(frozen=True)
class RedactionSettings:
    """Repository additions to redaction.

    ``patterns`` add secret detectors (name to regular expression). ``allow`` are exact values
    and ``allow_patterns`` regular expressions that are never masked. ``pii`` selects the personal
    data detectors. The entropy threshold applies to the generic ``key = value`` detector.
    """

    patterns: tuple[tuple[str, str], ...] = ()
    allow: tuple[str, ...] = ()
    allow_patterns: tuple[str, ...] = ()
    pii: frozenset[PiiKind] = field(default_factory=lambda: frozenset(PiiKind))
    entropy_threshold: float = 2.5

    def __post_init__(self) -> None:
        for name, pattern in self.patterns:
            compile_extra(name, pattern)
        for pattern in self.allow_patterns:
            try:
                re.compile(pattern)
            except re.error as error:
                raise RedactionSettingsError(
                    f"allow pattern {pattern!r} is invalid: {error}"
                ) from None
        if not 0 <= self.entropy_threshold <= 8:
            raise RedactionSettingsError("the entropy threshold must be between 0 and 8")

    def to_dict(self) -> dict[str, Any]:
        return {
            "patterns": dict(sorted(self.patterns)),
            "allow": sorted(self.allow),
            "allow_patterns": sorted(self.allow_patterns),
            "pii": sorted(kind.value for kind in self.pii),
            "entropy_threshold": self.entropy_threshold,
        }

    def digest(self) -> str:
        return hashlib.sha256(canonical_json(self.to_dict())).hexdigest()
