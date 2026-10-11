"""Gate 1: the attempt touched only what the task allowed, and not too much of it."""

import re
from collections.abc import Callable
from dataclasses import dataclass

from forja.checks.base import rejected
from forja.checks.changes import Changes, added_lines
from forja.core.adapters import FileClass
from forja.core.gates import Approved, Finding, GateInput, GateResult
from forja.orchestrator.ports import TaskInfo

SUPPRESSIONS = re.compile(
    r"noqa|fmt:\s*(?:off|on|skip)|yapf:\s*(?:disable|enable)|gitleaks:allow"
    r"|lizard\s+forgive|#\s*lizard|generated\s+code|nosem",
    re.IGNORECASE,
)
# Directories the tools write their caches to. The compiled files of Python are not here: the
# adapter sends them outside the worktree, so any that turn up inside it are suspect.
TOOL_CACHES = frozenset({".pytest_cache", ".ruff_cache", ".mypy_cache", ".hypothesis"})
CODE_SUFFIXES = (".py", ".pyi", ".pyw", ".pyz", ".pth", ".so", ".pyd", ".dll", ".zip")
COMPILED_SUFFIXES = (".pyc", ".pyo")
# What the interpreter names a cache file (PEP 3147): module.cpython-312.pyc, never importable
# as a module because of the dots in the name.
CACHE_NAME = re.compile(r"[^.]+\.[a-z0-9]+-\d+(?:\.opt-[12])?\.py[co]")


def disposable(path: str) -> bool:
    """Whether an ignored file is only a tool's cache and cannot be run or imported."""
    parts = path.replace("\\", "/").split("/")
    name, directories = parts[-1].lower(), parts[:-1]
    if name.endswith(COMPILED_SUFFIXES):
        return (
            bool(directories)
            and directories[-1] == "__pycache__"
            and bool(CACHE_NAME.fullmatch(name))
        )
    if name.endswith(CODE_SUFFIXES):
        return False
    return any(directory in TOOL_CACHES for directory in directories)


def in_scope(path: str, scope: tuple[str, ...]) -> bool:
    """Whether ``path`` is one of the scope entries or lies under one that is a directory."""
    normal = path.replace("\\", "/")
    for entry in scope:
        wanted = entry.replace("\\", "/").rstrip("/")
        if normal == wanted or normal.startswith(wanted + "/"):
            return True
    return False


def _limit(task_value: int, data: GateInput, name: str) -> int:
    """The stricter of the task's limit and the policy's; zero means neither set one."""
    limits = data.values.get("limits")
    from_policy = limits.get(name) if isinstance(limits, dict) else None
    policy = (
        from_policy if isinstance(from_policy, int) and not isinstance(from_policy, bool) else 0
    )
    chosen = [v for v in (task_value, policy) if v > 0]
    return min(chosen) if chosen else 0


@dataclass(frozen=True)
class ScopeCheck:
    """In a refactoring only production files in the task's scope may change; tests stay frozen."""

    changes: Changes
    task: TaskInfo
    classify: Callable[[str], FileClass]
    declared: tuple[str, ...] = ()  # what the agent said it changed; empty means not asked
    id: str = "scope"
    gate: int = 1
    requires: frozenset[str] = frozenset()

    async def evaluate(self, data: GateInput) -> GateResult:
        changes = self.changes
        if not changes.files:
            return rejected([Finding(message="the attempt changed nothing", target="diff")])
        findings = [
            *self._forbidden(),
            *self._hidden(),
            *self._suppressions(),
            *self._too_big(data),
            *self._undeclared(),
        ]
        return rejected(findings) if findings else Approved()

    def _forbidden(self) -> list[Finding]:
        findings = []
        for change in self.changes.files:
            for path in (change.old_path, change.path):
                if path is None:
                    continue
                kind = self.classify(path)
                if kind is not FileClass.PRODUCTION:
                    message = (
                        f"only production files may change in a refactoring (this is {kind.value})"
                    )
                    findings.append(Finding(message=message, target=path))
                elif not in_scope(path, self.task.scope):
                    findings.append(Finding(message="outside the task scope", target=path))
        return findings

    def _hidden(self) -> list[Finding]:
        """Files the ignore rules hide from the commit but not from the build and tests."""
        return [
            Finding(message="a file git ignores was added", target=path)
            for path in self.changes.ignored
            if not disposable(path)
        ]

    def _suppressions(self) -> list[Finding]:
        """A comment that tells a tool to look away is the tool being switched off."""
        return [
            Finding(
                message="a comment that silences a tool was added",
                target=line.path or "diff",
            )
            for line in added_lines(self.changes.patch)
            if SUPPRESSIONS.search(line.text)
        ]

    def _too_big(self, data: GateInput) -> list[Finding]:
        findings = []
        files = len(self.changes.files)
        max_files = _limit(self.task.max_files, data, "max_files")
        if max_files and files > max_files:
            message = "more files changed than the task allows"
            findings.append(
                Finding(message=message, target="diff", measured=files, limit=max_files)
            )
        lines = self.changes.lines
        max_lines = _limit(self.task.max_lines, data, "max_lines")
        if max_lines and lines > max_lines:
            message = "more lines changed than the task allows"
            findings.append(
                Finding(message=message, target="diff", measured=lines, limit=max_lines)
            )
        return findings

    def _undeclared(self) -> list[Finding]:
        if not self.declared:
            return []
        changed = {c.path for c in self.changes.files}
        declared = {path.replace("\\", "/") for path in self.declared}
        if changed == declared:
            return []
        missing, extra = sorted(declared - changed), sorted(changed - declared)
        detail = "; ".join(
            part
            for part in (
                f"declared but not changed: {', '.join(missing)}" if missing else "",
                f"changed but not declared: {', '.join(extra)}" if extra else "",
            )
            if part
        )
        return [
            Finding(
                message=f"the declared files differ from the changed ones ({detail})", target="diff"
            )
        ]
