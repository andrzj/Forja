"""Gate 2: the dependencies an attempt adds are installed before anything runs.

The tests and the build of an attempt need the packages its manifest now declares. Before that, each
new name is proven to exist in the registry (a name the agent invented is never installed), then the
requirements of the new names are installed. Anything that stops this rejects the attempt with what
stopped it. Age and use of the dependency are judged later, by gate 10.
"""

import re
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from forja.checks.base import decided, rejected
from forja.checks.changes import Changes
from forja.checks.new_dependency import (
    Declared,
    Manifests,
    added_dependencies,
    unproven_dependencies,
)
from forja.checks.registries import HttpGet, urllib_get
from forja.core.gates import Approved, Finding, GateInput, GateResult

ECOSYSTEM = "PyPI"  # the only registry that has an installer

# (path, text) -> the whole requirements a manifest declares, for the installer
Requirements = Callable[[str, str], frozenset[str]]
# installs the requirements; the error text when it could not, else None
Installer = Callable[[frozenset[str]], Awaitable[str | None]]

_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


def _normal(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _named(requirement: str) -> str:
    found = _NAME.match(requirement)
    return _normal(found[0]) if found else ""


def requirements_of(adapters: Iterable[Any]) -> Requirements:
    """The requirements the language adapters read; an adapter that installs has
    ``declared_requirements``, outside its ``Protocol``."""
    known = tuple(adapters)

    def declared(path: str, text: str) -> frozenset[str]:
        for adapter in known:
            read = getattr(adapter, "declared_requirements", None)
            found = read(path, text) if callable(read) else frozenset()
            if found:
                return frozenset(found)
        return frozenset()

    return declared


def python_manifests(manifests: Manifests) -> Manifests:
    """The manifests of the registry that has an installer."""

    def declared(path: str, text: str) -> Declared | None:
        found = manifests(path, text)
        return found if found is not None and found.ecosystem == ECOSYSTEM else None

    return declared


async def install_findings(
    worktree: Path,
    changes: Changes,
    before: dict[str, str],
    manifests: Manifests,
    requirements: Requirements,
    install: Installer,
    get: HttpGet = urllib_get,
) -> list[Finding]:
    """What stops the attempt: a new name the registry does not list or cannot be asked about,
    or an installer that failed. Empty when the new ones are installed, or there are none."""
    own = python_manifests(manifests)
    unproven = await unproven_dependencies(worktree, changes, before, own, get)
    if unproven:
        return unproven
    added, _ = added_dependencies(worktree, changes, before, own)
    wanted: set[str] = set()
    for (path, _declared), names in added.items():
        new = {_normal(name) for name in names}
        text = (worktree / path).read_text(encoding="utf-8")
        wanted |= {item for item in requirements(path, text) if _named(item) in new}
    if not wanted:
        return []
    failure = await install(frozenset(wanted))
    if failure:
        message = f"installing {', '.join(sorted(wanted))} failed: {failure}"
        return [Finding(message=message, target=min(path for path, _ in added))]
    return []


@dataclass(frozen=True)
class DependencyInstallCheck:
    """The verdict of ``install_findings``, which ran before the checks so that the checks run in
    the environment it made."""

    findings: tuple[Finding, ...]
    id: str = "dependency_install"
    gate: int = 2
    requires: frozenset[str] = frozenset()

    async def evaluate(self, data: GateInput) -> GateResult:
        async def judge() -> GateResult:
            return rejected(list(self.findings)) if self.findings else Approved()

        return await decided(judge())
