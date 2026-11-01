"""Gate 10: a dependency the attempt added exists in the official registry, and is not brand new
or unused.

An agent can invent a package with a plausible name, and an attacker can register that name
afterwards. So every name added to a manifest is looked up in the registry of its ecosystem: it
must exist, it must have been published at least ``min_age_days`` ago and, where the registry
counts downloads (npm: last week, NuGet: total), have at least ``min_downloads``. A registry that
cannot be reached, or does not say, is inconclusive: never a pass. This check only rejects or
reports; the decision record that a new dependency calls for is the documenter's.
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from forja.checks.base import Undecided, decided, rejected
from forja.checks.changes import Change, ChangeKind, Changes
from forja.checks.registries import HttpGet, Missing, Standing, Unreachable, look_up, urllib_get
from forja.core.gates import (
    Approved,
    Finding,
    GateInput,
    GateResult,
    Inconclusive,
    InconclusiveReason,
)

DEFAULT_MIN_AGE_DAYS = 30
DEFAULT_MIN_DOWNLOADS = 100
MAX_LOOKUPS = 50  # a manifest rewritten from scratch is not looked up name by name forever


@dataclass(frozen=True)
class Declared:
    """The dependencies one manifest declares."""

    language: str  # the language whose thresholds apply
    ecosystem: str  # the registry: npm, PyPI, Go, Maven or NuGet
    names: frozenset[str]


# (path, text) -> what the manifest declares, None when the path is not a manifest, and
# ValueError when it is one that cannot be read
Manifests = Callable[[str, str], Declared | None]


def manifests_of(adapters: Iterable[Any]) -> Manifests:
    """The manifests the language adapters read. Reading them is a capability an adapter may
    have (``dependency_ecosystem`` and ``declared_dependencies``), outside its ``Protocol``."""

    known = tuple(adapters)  # an iterator would be spent by the first path asked about

    def declared(path: str, text: str) -> Declared | None:
        for adapter in known:
            read = getattr(adapter, "declared_dependencies", None)
            names = read(path, text) if callable(read) else None
            if names is not None:
                return Declared(adapter.language, adapter.dependency_ecosystem, names)
        return None

    return declared


def is_manifest(manifests: Manifests, path: str) -> bool:
    """Whether the name alone says a manifest (one that does not parse empty says it too)."""
    try:
        return manifests(path, "") is not None
    except ValueError:
        return True


def dependency_edit_of(
    adapters: Iterable[Any], worktree: Path, before: dict[str, str]
) -> Callable[[Change], bool]:
    """Whether a change is an edit of a manifest that touches only its dependencies. That is what
    an adapter says through ``only_dependencies_changed`` (a capability outside its ``Protocol``,
    as ``declared_dependencies`` is); a language without it has no manifest the agent may edit.
    A rename, a copy and a deletion are never one."""

    known = tuple(adapters)

    def edit(change: Change) -> bool:
        if change.kind not in (ChangeKind.ADDED, ChangeKind.MODIFIED) or change.old_path:
            return False
        try:
            after = (worktree / change.path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return False
        was = "" if change.kind is ChangeKind.ADDED else before.get(change.path, "")
        for adapter in known:
            judge = getattr(adapter, "only_dependencies_changed", None)
            verdict = judge(change.path, was, after) if callable(judge) else None
            if verdict is not None:
                return bool(verdict)
        return False

    return edit


def threshold(data: GateInput, language: str, name: str, default: int) -> int:
    thresholds = data.values.get("thresholds")
    per_language = thresholds.get(language) if isinstance(thresholds, dict) else None
    value = per_language.get(name) if isinstance(per_language, dict) else None
    return int(value) if isinstance(value, int | float) and value >= 0 else default


def added_dependencies(
    worktree: Path, changes: Changes, before: dict[str, str], manifests: Manifests
) -> tuple[dict[tuple[str, Declared], frozenset[str]], list[str]]:
    """Per changed manifest, the names the attempt put in it, and the manifests that could not
    be read: what is in them is unknown, so they are never taken for empty."""
    found: dict[tuple[str, Declared], frozenset[str]] = {}
    unreadable: list[str] = []
    for change in changes.files:
        if not change.exists_now:
            continue
        try:
            text = (worktree / change.path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            if is_manifest(manifests, change.path):  # one that cannot be read is not an empty one
                unreadable.append(change.path)
            continue
        try:
            declared = manifests(change.path, text)
            old = before.get(change.before or "")
            was = manifests(change.before or "", old) if old is not None else None
        except ValueError:
            unreadable.append(change.path)
            continue
        if declared is None:
            continue
        new = declared.names - (was.names if was is not None else frozenset())
        if new:
            found[(change.path, declared)] = new
    return found, unreadable


@dataclass(frozen=True)
class NewDependencyCheck:
    worktree: Path
    changes: Changes
    before: dict[str, str]  # the parent commit's text of the changed manifests, by old path
    manifests: Manifests
    get: HttpGet = urllib_get
    now: Callable[[], datetime] = lambda: datetime.now(UTC)  # noqa: E731
    id: str = "new_dependency"
    gate: int = 10
    requires: frozenset[str] = frozenset()

    async def evaluate(self, data: GateInput) -> GateResult:
        return await decided(self._judge(data))

    async def _judge(self, data: GateInput) -> GateResult:
        added, unreadable = self._added()
        if not added and not unreadable:
            return Approved()
        total = sum(len(names) for names in added.values())
        if total > MAX_LOOKUPS:
            raise Undecided(
                Inconclusive(
                    reason=InconclusiveReason.TOOL_FAILED,
                    detail=f"new_dependency: {total} new dependencies (limit {MAX_LOOKUPS})",
                )
            )
        findings: list[Finding] = []
        unknown: list[str] = [f"{path} (unreadable)" for path in unreadable]
        for (path, declared), names in added.items():
            for name in sorted(names):
                try:
                    standing = await look_up(declared.ecosystem, name, self.get)
                except Missing:
                    findings.append(
                        Finding(
                            message=f"{name} does not exist in the {declared.ecosystem} registry",
                            target=path,
                        )
                    )
                    continue
                except Unreachable:
                    unknown.append(name)
                    continue
                findings += self._doubts(data, path, declared, name, standing)
                if standing.first_published is None:
                    unknown.append(name)
        if findings:
            return rejected(findings)
        if unknown:
            raise Undecided(
                Inconclusive(
                    reason=InconclusiveReason.TOOL_FAILED,
                    detail="new_dependency: could not verify "
                    + ", ".join(sorted(set(unknown))[:3]),
                )
            )
        return Approved()

    def _added(self) -> tuple[dict[tuple[str, Declared], frozenset[str]], list[str]]:
        return added_dependencies(self.worktree, self.changes, self.before, self.manifests)

    def _doubts(
        self, data: GateInput, path: str, declared: Declared, name: str, standing: Standing
    ) -> list[Finding]:
        findings = []
        language = declared.language
        min_age = threshold(data, language, "min_age_days", DEFAULT_MIN_AGE_DAYS)
        if standing.first_published is not None:
            age = (self.now() - standing.first_published).days
            if age < min_age:
                message = f"{name} was first published {age} day(s) ago (minimum {min_age})"
                findings.append(Finding(message=message, target=path, measured=age, limit=min_age))
        min_downloads = threshold(data, language, "min_downloads", DEFAULT_MIN_DOWNLOADS)
        if standing.downloads is not None and standing.downloads < min_downloads:
            message = f"{name} has {standing.downloads} download(s) (minimum {min_downloads})"
            findings.append(
                Finding(
                    message=message, target=path, measured=standing.downloads, limit=min_downloads
                )
            )
        return findings
