"""Redaction of what Forja sends to a model (contract: security and data governance).

A deterministic stage that runs before any send. It masks secrets and personal data, drops files
marked sensitive, and fails closed: whatever it cannot process is withheld, never sent as it was.
The same value gets the same mask inside one package, so the model can still see that two places
use the same secret, but masks are numbered by order of appearance and never derived from the value.
"""

import logging
import re
from bisect import bisect_right
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum

from forja.core.artifacts.models import Assumption
from forja.core.isolation.sensitive import SensitivePaths
from forja.core.redaction.pii import DETECTORS
from forja.core.redaction.rules import RULES, is_placeholder, rules_version, shannon_entropy
from forja.core.redaction.settings import (
    MAX_ITEM_CHARS,
    MAX_LINE_CHARS,
    RedactionSettings,
    compile_extra,
)

_logger = logging.getLogger("forja.redaction")
GENERIC_RULE = "generic-credential"
LONG_LINE_MASK = "[REDACTED:long-line]"
_PLACEHOLDER_CHECK_LIMIT = 200  # long values are blocks of key material, never placeholders


class ItemKind(StrEnum):
    FILE = "file"
    EVIDENCE = "evidence"
    TEXT = "text"


class Category(StrEnum):
    SECRET = "secret"
    PII = "pii"
    LONG_LINE = "long_line"


class DropReason(StrEnum):
    SENSITIVE_FILE = "sensitive_file"
    BINARY = "binary"
    TOO_LARGE = "too_large"
    ERROR = "error"


_DROP_TEXT = {
    DropReason.SENSITIVE_FILE: "it matches the sensitive-file patterns",
    DropReason.BINARY: "it is not text",
    DropReason.TOO_LARGE: "it is larger than the limit for one item",
    DropReason.ERROR: "redacting it failed, so it was withheld to be safe",
}


@dataclass(frozen=True)
class PackageItem:
    """One piece of the package. ``essential`` marks what the task cannot do without."""

    kind: ItemKind
    name: str
    content: str
    essential: bool = False


@dataclass(frozen=True)
class RedactedItem:
    kind: ItemKind
    name: str
    content: str


@dataclass(frozen=True)
class Finding:
    """Where something was masked. It never holds the value, a hash of it, or its length."""

    category: Category
    rule: str
    item: str
    line: int
    placeholder: str


@dataclass(frozen=True)
class Dropped:
    name: str
    kind: ItemKind
    reason: DropReason


@dataclass(frozen=True)
class RedactionResult:
    items: tuple[RedactedItem, ...]
    dropped: tuple[Dropped, ...]
    findings: tuple[Finding, ...]
    assumptions: tuple[Assumption, ...]
    rules_version: str


@dataclass(frozen=True)
class _Match:
    start: int
    end: int
    category: Category
    rule: str
    value: str


def is_essential(name: str, scope: Iterable[str], cited_paths: Iterable[str]) -> bool:
    """A file is essential if the task is declared to touch it or something cites it."""
    normal = name.replace("\\", "/")
    return normal in set(scope) or normal in set(cited_paths)


class Redactor:
    def __init__(
        self, settings: RedactionSettings | None = None, sensitive: SensitivePaths | None = None
    ) -> None:
        self._settings = settings or RedactionSettings()
        self._sensitive = sensitive or SensitivePaths.with_defaults()
        self._extra = [
            (f"custom-{name}", compile_extra(name, pattern))
            for name, pattern in self._settings.patterns
        ]
        self._allow_values = frozenset(self._settings.allow)
        self._allow_patterns = [re.compile(p) for p in self._settings.allow_patterns]
        self._detectors = [d for d in DETECTORS if d.kind in self._settings.pii]

    def redact(self, items: Sequence[PackageItem]) -> RedactionResult:
        secret_ids: dict[str, int] = {}
        pii_ids: dict[str, int] = {}
        kept: list[RedactedItem] = []
        dropped: list[Dropped] = []
        findings: list[Finding] = []
        assumptions: list[Assumption] = []

        for item in items:
            reason = self._refusal(item)
            if reason is None:
                try:
                    content, item_findings = self._mask(item, secret_ids, pii_ids)
                except Exception:
                    _logger.exception("redacting %s failed; the item is withheld", item.name)
                    reason = DropReason.ERROR
            if reason is not None:
                dropped.append(Dropped(item.name, item.kind, reason))
                if item.essential:
                    assumptions.append(_withheld(item.name, reason))
                continue
            kept.append(RedactedItem(item.kind, item.name, content))
            findings.extend(item_findings)
            if item.essential and any(f.category is not Category.LONG_LINE for f in item_findings):
                assumptions.append(_masked(item.name, item_findings))

        return RedactionResult(
            tuple(kept), tuple(dropped), tuple(findings), tuple(assumptions), rules_version()
        )

    # -- decisions about a whole item ----------------------------------------------------------

    def _refusal(self, item: PackageItem) -> DropReason | None:
        if item.kind is ItemKind.FILE and self._sensitive.matches(item.name):
            return DropReason.SENSITIVE_FILE
        if chr(0) in item.content:
            return DropReason.BINARY
        if len(item.content) > MAX_ITEM_CHARS:
            return DropReason.TOO_LARGE
        return None

    # -- masking inside an item ----------------------------------------------------------------

    def _mask(
        self, item: PackageItem, secret_ids: dict[str, int], pii_ids: dict[str, int]
    ) -> tuple[str, list[Finding]]:
        text, long_lines = _shorten_long_lines(item.content)
        starts = _line_starts(text)
        found = _merge_overlaps(self._matches(text), text)

        findings = [
            Finding(Category.LONG_LINE, "long-line", item.name, line, LONG_LINE_MASK)
            for line in long_lines
        ]
        pieces: list[str] = []
        cursor = 0
        for match in found:
            ids = secret_ids if match.category is Category.SECRET else pii_ids
            number = ids.setdefault(match.value, len(ids) + 1)
            label = "REDACTED" if match.category is Category.SECRET else "PII"
            placeholder = f"[{label}:{match.rule}:{number}]"
            pieces.append(text[cursor : match.start])
            pieces.append(placeholder)
            cursor = match.end
            findings.append(
                Finding(
                    match.category,
                    match.rule,
                    item.name,
                    bisect_right(starts, match.start),
                    placeholder,
                )
            )
        pieces.append(text[cursor:])
        findings.sort(key=lambda f: f.line)
        return "".join(pieces), findings

    def _matches(self, text: str) -> list[_Match]:
        return [
            *self._rule_matches(text),
            *self._extra_matches(text),
            *self._pii_matches(text),
        ]

    def _rule_matches(self, text: str) -> list[_Match]:
        lowered = text.lower()
        matches: list[_Match] = []
        for rule in RULES:
            if rule.keywords and not any(word in lowered for word in rule.keywords):
                continue
            for hit in rule.pattern.finditer(text):
                value = hit.group(rule.group)
                if not value or self._allowed(value) or (rule.check and not rule.check(value)):
                    continue
                if len(value) <= _PLACEHOLDER_CHECK_LIMIT and is_placeholder(value):
                    continue  # documentation keys and fillers, whatever rule found them
                floor = (
                    self._settings.entropy_threshold if rule.uses_threshold else rule.min_entropy
                )
                if floor is not None and shannon_entropy(value) < floor:
                    continue
                start, end = hit.span(rule.group)
                matches.append(_Match(start, end, Category.SECRET, rule.id, value))
        return matches

    def _extra_matches(self, text: str) -> list[_Match]:
        matches: list[_Match] = []
        for name, pattern in self._extra:
            for hit in pattern.finditer(text):
                group = 1 if pattern.groups else 0
                value = hit.group(group)
                if value and not self._allowed(value):
                    start, end = hit.span(group)
                    matches.append(_Match(start, end, Category.SECRET, name, value))
        return matches

    def _pii_matches(self, text: str) -> list[_Match]:
        matches: list[_Match] = []
        for detector in self._detectors:
            for pattern in detector.patterns:
                for hit in pattern.finditer(text):
                    value = hit.group(0)
                    if detector.valid(value) and not self._allowed(value):
                        matches.append(
                            _Match(hit.start(), hit.end(), Category.PII, detector.kind.value, value)
                        )
        return matches

    def _allowed(self, value: str) -> bool:
        return (
            value in self._allow_values
            or value.startswith(
                ("[REDACTED:", "[PII:")
            )  # our own masks, so redacting twice is a no-op
            or any(p.fullmatch(value) for p in self._allow_patterns)
        )


# -- helpers ---------------------------------------------------------------------------------


def _shorten_long_lines(content: str) -> tuple[str, list[int]]:
    if len(content) <= MAX_LINE_CHARS:
        return content, []
    lines = content.split("\n")
    long_lines = [
        number for number, line in enumerate(lines, start=1) if len(line) > MAX_LINE_CHARS
    ]
    if not long_lines:
        return content, []
    for number in long_lines:
        lines[number - 1] = LONG_LINE_MASK
    return "\n".join(lines), long_lines


def _line_starts(text: str) -> list[int]:
    starts = [0]
    starts.extend(index + 1 for index, char in enumerate(text) if char == "\n")
    return starts


def _merge_overlaps(matches: list[_Match], text: str) -> list[_Match]:
    """Join matches that overlap into one, so no part of a secret is left outside a mask.

    The joined span takes the category and rule of a secret if any of its parts is one; among the
    same category the longest part names it. The mask covers the whole joined text.
    """
    merged: list[_Match] = []
    group: list[_Match] = []
    group_end = -1
    for match in sorted(matches, key=lambda m: (m.start, -(m.end - m.start))):
        if group and match.start >= group_end:
            merged.append(_join(group, text))
            group = []
        group.append(match)
        group_end = max(group_end, match.end) if len(group) > 1 else match.end
    if group:
        merged.append(_join(group, text))
    return merged


def _join(group: list[_Match], text: str) -> _Match:
    start = min(m.start for m in group)
    end = max(m.end for m in group)
    leader = min(
        group,
        key=lambda m: (
            m.category is not Category.SECRET,
            -(m.end - m.start),
            m.rule == GENERIC_RULE,  # a specific rule names the match better than the generic one
            m.rule,
        ),
    )
    return _Match(start, end, leader.category, leader.rule, text[start:end])


def _withheld(name: str, reason: DropReason) -> Assumption:
    return Assumption(
        statement=f"The content of {name} was withheld from the model",
        reason=_DROP_TEXT[reason],
        missing_evidence=f"the content of {name}",
    )


def _masked(name: str, findings: Sequence[Finding]) -> Assumption:
    rules = sorted({f.rule for f in findings if f.category is not Category.LONG_LINE})
    return Assumption(
        statement=f"Some values in {name} were masked before it was sent to the model",
        reason=f"{len(findings)} value(s) matched redaction rules: {', '.join(rules)}",
        missing_evidence="the original values",
    )
