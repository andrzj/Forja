"""Gate 14: a task that brings a new external dependency or a new module owes an ADR.

A rule, not a model, decides that a decision record is called for; the documenter writes it. The
detectors are the manifests the adapters read (a name the task added) and the directory (the unit
of a module): a directory with a production file the task added and none at the task's base. It
does not look at the graph between modules or at layer rules.

The check wants one new numbered record under ``docs/adr`` with a section on the alternatives and
one on the consequences, whenever a detector fires. A record nobody asked for is not rejected.
"""

import posixpath
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from forja.checks.base import decided, rejected
from forja.checks.readme import chunks
from forja.core.gates import Approved, Finding, GateInput, GateResult

ADR_DIR = "docs/adr"
DEPENDENCY, MODULE = "dependency", "module"
_NAME = re.compile(r"^(\d{4,})-.+\.md$", re.IGNORECASE)
REQUIRED = (
    ("alternatives", r"alternativ"),
    ("consequences", r"consequ|trade-?off|compromiss"),
)


@dataclass(frozen=True)
class Trigger:
    kind: str
    subject: str  # the dependency or the directory
    where: str  # the manifest that declares it, or the first file of the module

    def describe(self) -> str:
        what = "external dependency" if self.kind == DEPENDENCY else "module"
        return f"new {what} `{self.subject}` ({self.where})"


def new_modules(
    added: Iterable[str], production_before: Iterable[str], production_now: set[str]
) -> list[Trigger]:
    """Directories whose production files the task added and that had none at the base."""
    old = {posixpath.dirname(path) for path in production_before}
    found: dict[str, str] = {}
    for path in sorted(added):
        folder = posixpath.dirname(path)
        if path in production_now and folder and folder not in old:
            found.setdefault(folder, path)
    return [Trigger(MODULE, folder, first) for folder, first in found.items()]


def numbers_in(paths: Iterable[str]) -> set[int]:
    """The numbers of the records among ``paths`` (those under ``docs/adr``)."""
    found = set()
    for path in paths:
        folder, name = posixpath.split(path)
        match = _NAME.match(name)
        if folder == ADR_DIR and match:
            found.add(int(match.group(1)))
    return found


def next_number(paths: Iterable[str]) -> int:
    return max(numbers_in(paths), default=0) + 1


def missing_sections(text: str) -> list[str]:
    headings = [part.heading for part in chunks(text) if part.heading]
    return [
        name
        for name, pattern in REQUIRED
        if not any(re.search(pattern, heading, re.IGNORECASE) for heading in headings)
    ]


def report(triggers: list[Trigger], paths: Iterable[str]) -> str:
    """What the documenter is told when a record is owed; empty when none is."""
    if not triggers:
        return ""
    number = f"{next_number(paths):04d}"
    lines = [f"- {trigger.describe()}" for trigger in triggers]
    lines.append(
        f"Write one decision record at `{ADR_DIR}/{number}-<short-title>.md` with sections for the "
        "context, the decision, the alternatives and the consequences (trade-offs)."
    )
    return "\n".join(lines)


@dataclass(frozen=True)
class AdrCheck:
    worktree: Path
    triggers: tuple[Trigger, ...]
    before: frozenset[str]  # the records the stage began with, as repository paths
    id: str = "adr"
    gate: int = 14
    requires: frozenset[str] = frozenset()

    async def evaluate(self, data: GateInput) -> GateResult:
        return await decided(self._judge())

    async def _judge(self) -> GateResult:
        if not self.triggers:
            return Approved()
        why = "; ".join(trigger.describe() for trigger in self.triggers)
        written = self._written()
        if not written:
            return rejected(
                [Finding(message=f"{why}: the task owes a record under {ADR_DIR}", target=ADR_DIR)]
            )
        used = numbers_in(self.before)
        problems: list[Finding] = []
        for path, text in written.items():
            found = [
                Finding(message=f"the record has no section on the {name}", target=path)
                for name in missing_sections(text)
            ]
            number = int(path.rsplit("/", 1)[-1].split("-", 1)[0])
            if number in used:
                found.append(Finding(message=f"record number {number} is taken", target=path))
            if not found:  # one good record answers the rule
                return Approved()
            problems += found
        return rejected(problems)

    def _written(self) -> dict[str, str]:
        """The records the stage added, by repository path; links and unreadable files are left."""
        folder = self.worktree / ADR_DIR
        if not folder.is_dir() or folder.is_symlink():
            return {}
        found = {}
        for entry in sorted(folder.iterdir()):
            relative = f"{ADR_DIR}/{entry.name}"
            if relative in self.before or not _NAME.match(entry.name):
                continue
            if entry.is_symlink() or not entry.is_file():
                continue
            try:
                found[relative] = entry.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
        return found
