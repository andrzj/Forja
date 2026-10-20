"""Gate 3: the files are in the canonical format, and lint has no new violation (the ratchet)."""

import tempfile
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from forja.checks.base import decided, measure, overrides_from, rejected
from forja.checks.changes import Changes, write_files
from forja.checks.tooling import Tools
from forja.core.adapters import EvidenceDraft, LanguageAdapter, Operation, OperationRequest
from forja.core.gates import Approved, Finding, GateInput, GateResult

LINT_CONFIG = ("pyproject.toml", "ruff.toml", ".ruff.toml", "setup.cfg")


@dataclass(frozen=True)
class FormatCheck:
    """Whatever the attempt wrote must already be what the formatter would write."""

    tools: Tools
    adapter: LanguageAdapter
    worktree: Path
    changes: Changes
    accepts: Callable[[str], bool]  # the files the adapter formats
    id: str = "format"
    gate: int = 3
    requires: frozenset[str] = frozenset()

    async def evaluate(self, data: GateInput) -> GateResult:
        return await decided(self._judge(data))

    async def _judge(self, data: GateInput) -> GateResult:
        files = self.changes.current(self.accepts)
        if not files:
            return Approved()
        request = OperationRequest(root=self.worktree, files=files, check_only=True)
        overrides = overrides_from(self.adapter, data.values)
        parsed = await measure(
            self.tools, self.adapter, Operation.FORMAT, "format", request, overrides
        )
        findings = []
        for draft in parsed.drafts:
            if draft.measurement == "format.invalid_syntax":
                message = "the file does not parse"
            else:
                message = "the file is not in the canonical format"
            findings.append(Finding(message=message, target=draft.target.id))
        return rejected(findings) if findings else Approved()


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
    does not make an old violation look new.
    """

    tools: Tools
    adapter: LanguageAdapter
    worktree: Path
    changes: Changes
    before: dict[str, str]  # the parent commit's text of the changed files, by old path
    accepts: Callable[[str], bool]  # the files the adapter lints
    id: str = "lint"
    gate: int = 3
    requires: frozenset[str] = frozenset()

    async def evaluate(self, data: GateInput) -> GateResult:
        return await decided(self._judge(data))

    async def _judge(self, data: GateInput) -> GateResult:
        files = self.changes.current(self.accepts)
        if not files:
            return Approved()
        overrides = overrides_from(self.adapter, data.values)
        request = OperationRequest(root=self.worktree, files=files)
        after = violations((await measure(
            self.tools, self.adapter, Operation.LINT, "lint", request, overrides
        )).drafts)  # fmt: skip
        was = await self._before(overrides)
        findings = []
        for (path, rule), count in sorted(after.items()):
            old = was[(self._origin(path), rule)]
            if count > old:
                message = f"{count - old} new {rule} violation(s)"
                findings.append(Finding(message=message, target=path, measured=count, limit=old))
        return rejected(findings) if findings else Approved()

    def _origin(self, path: str) -> str:
        """Where the file was before this attempt: its old name if it was renamed."""
        for change in self.changes.files:
            if change.path == path:
                return change.before or path
        return path

    async def _before(
        self, overrides: dict[str, dict[str, tuple[str, ...]]]
    ) -> Counter[tuple[str, str]]:
        """Lint of the parent commit's version of the same files, in a private directory."""
        if not self.before:
            return Counter()
        with tempfile.TemporaryDirectory(prefix="forja-before-") as directory:
            root = Path(directory)
            write_files(self.before, root)
            for name in LINT_CONFIG:
                if (self.worktree / name).is_file():
                    (root / name).write_bytes((self.worktree / name).read_bytes())
            request = OperationRequest(root=root, files=tuple(sorted(self.before)))
            parsed = await measure(
                self.tools, self.adapter, Operation.LINT, "lint_before", request, overrides
            )
            return violations(parsed.drafts)
