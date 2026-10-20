"""Gate 3: the files are in the canonical format, and lint has no new violation (the ratchet).

Each file goes to the adapter that claims it. An adapter that offers no such operation (a linter
the project does not use) leaves its files alone; the check is not applicable only when none does.
"""

import shutil
import tempfile
from collections import Counter
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

from forja.checks.base import Undecided, decided, measure, overrides_from, rejected
from forja.checks.changes import ChangeKind, Changes, write_files
from forja.checks.tooling import Tools
from forja.core.adapters import (
    AdapterRegistry,
    EvidenceDraft,
    LanguageAdapter,
    Operation,
    OperationRequest,
    Parsed,
)
from forja.core.gates import (
    Approved,
    Finding,
    GateInput,
    GateResult,
    Inconclusive,
    InconclusiveReason,
    NotApplicable,
)


def by_adapter(
    adapters: AdapterRegistry, files: tuple[str, ...]
) -> list[tuple[LanguageAdapter, tuple[str, ...]]]:
    """The files of each adapter, adapters in registration order, files in the order given."""
    groups: dict[str, list[str]] = {}
    for path in files:
        adapter = adapters.for_file(path)
        if adapter is not None:
            groups.setdefault(adapter.language, []).append(path)
    return [(adapters.language(name), tuple(paths)) for name, paths in groups.items()]


def own_files(adapters: AdapterRegistry) -> Callable[[str], bool]:
    return lambda path: adapters.for_file(path) is not None


async def measured(probe: Awaitable[Parsed]) -> Parsed | None:
    """What the operation measured, ``None`` when the adapter does not offer it."""
    try:
        return await probe
    except Undecided as stop:
        if isinstance(stop.result, NotApplicable):
            return None
        raise


@dataclass(frozen=True)
class FormatCheck:
    """Whatever the attempt wrote must already be what the formatter would write."""

    tools: Tools
    adapters: AdapterRegistry
    worktree: Path
    changes: Changes
    id: str = "format"
    gate: int = 3
    requires: frozenset[str] = frozenset()

    async def evaluate(self, data: GateInput) -> GateResult:
        return await decided(self._judge(data))

    async def _judge(self, data: GateInput) -> GateResult:
        files = self.changes.current(own_files(self.adapters))
        if not files:
            return Approved()
        findings: list[Finding] = []
        offered = False
        for adapter, own in by_adapter(self.adapters, files):
            request = OperationRequest(root=self.worktree, files=own, check_only=True)
            overrides = overrides_from(adapter, data.values)
            parsed = await measured(
                measure(self.tools, adapter, Operation.FORMAT, "format", request, overrides)
            )
            if parsed is None:
                continue
            offered = True
            for draft in parsed.drafts:
                if draft.measurement == "format.invalid_syntax":
                    message = "the file does not parse"
                else:
                    message = "the file is not in the canonical format"
                findings.append(Finding(message=message, target=draft.target.id))
        if not offered:
            return NotApplicable(missing_capability=Operation.FORMAT.value)
        return rejected(findings) if findings else Approved()


def _skip_git_and_links(directory: str, names: list[str]) -> set[str]:
    """What the private copy leaves out: git's own directory and any link, which could lead out of
    the copy when the old texts are written into it."""
    base = Path(directory)
    return {n for n in names if n == ".git" or (base / n).is_symlink() or (base / n).is_junction()}


def violations(drafts: tuple[EvidenceDraft, ...]) -> Counter[tuple[str, str]]:
    """Violations per (file, rule)."""
    counts: Counter[tuple[str, str]] = Counter()
    for draft in drafts:
        counts[(draft.target.id, draft.measurement.removeprefix("lint."))] += int(draft.value)
    return counts


@dataclass(frozen=True)
class LintCheck:
    """Only violations the attempt added reprove: the old ones are a task for the planner.

    A violation is counted per file and rule, so moving code inside a file, or renaming the file,
    does not make an old violation look new. An adapter whose linter runs on the new files but not
    on the old version has nothing to compare with: the answer is inconclusive, never a pass.
    """

    tools: Tools
    adapters: AdapterRegistry
    worktree: Path
    changes: Changes
    before: dict[str, str]  # the parent commit's text of the changed files, by old path
    id: str = "lint"
    gate: int = 3
    requires: frozenset[str] = frozenset()

    async def evaluate(self, data: GateInput) -> GateResult:
        return await decided(self._judge(data))

    async def _judge(self, data: GateInput) -> GateResult:
        files = self.changes.current(own_files(self.adapters))
        if not files:
            return Approved()
        findings: list[Finding] = []
        offered = False
        for adapter, own in by_adapter(self.adapters, files):
            overrides = overrides_from(adapter, data.values)
            request = OperationRequest(root=self.worktree, files=own)
            parsed = await measured(
                measure(self.tools, adapter, Operation.LINT, "lint", request, overrides)
            )
            if parsed is None:
                continue
            was = await self._before(adapter, overrides)
            if was is None:
                raise Undecided(
                    Inconclusive(
                        reason=InconclusiveReason.TOOL_FAILED,
                        detail=f"lint: the {adapter.language} linter cannot run on the old files",
                    )
                )
            offered = True
            for (path, rule), count in sorted(violations(parsed.drafts).items()):
                old = was[(self._origin(path), rule)]
                if count > old:
                    message = f"{count - old} new {rule} violation(s)"
                    findings.append(
                        Finding(message=message, target=path, measured=count, limit=old)
                    )
        if not offered:
            return NotApplicable(missing_capability=Operation.LINT.value)
        return rejected(findings) if findings else Approved()

    def _origin(self, path: str) -> str:
        """Where the file was before this attempt: its old name if it was renamed."""
        for change in self.changes.files:
            if change.path == path:
                return change.before or path
        return path

    async def _before(
        self, adapter: LanguageAdapter, overrides: dict[str, dict[str, tuple[str, ...]]]
    ) -> Counter[tuple[str, str]] | None:
        """Lint of the parent commit's version of the adapter's files, in a private copy of the
        worktree turned back into that commit: a linter that type-checks needs the files next to
        the ones it is asked about. ``None`` when the linter cannot run there."""
        texts = {
            path: text
            for path, text in self.before.items()
            if self.adapters.for_file(path) is adapter
        }
        if not texts:
            return Counter()
        with tempfile.TemporaryDirectory(prefix="forja-before-") as directory:
            root = Path(directory)
            shutil.copytree(
                self.worktree,
                root,
                symlinks=True,
                dirs_exist_ok=True,
                ignore=_skip_git_and_links,
            )
            for change in self.changes.files:
                if change.kind in (ChangeKind.ADDED, ChangeKind.RENAMED):
                    (root / change.path).unlink(missing_ok=True)
            write_files(texts, root)
            request = OperationRequest(root=root, files=tuple(sorted(texts)))
            parsed = await measured(
                measure(self.tools, adapter, Operation.LINT, "lint_before", request, overrides)
            )
            return None if parsed is None else violations(parsed.drafts)
