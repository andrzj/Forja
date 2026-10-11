"""Gate 1: the attempt touched only what the task allowed, and not too much of it."""

from collections.abc import Callable
from dataclasses import dataclass

from forja.checks.base import rejected
from forja.checks.changes import Changes
from forja.core.adapters import FileClass
from forja.core.gates import Approved, Finding, GateInput, GateResult
from forja.orchestrator.ports import TaskInfo


def in_scope(path: str, scope: tuple[str, ...]) -> bool:
    """Whether ``path`` is one of the scope entries or lies under one that is a directory."""
    normal = path.replace("\\", "/")
    for entry in scope:
        wanted = entry.replace("\\", "/").rstrip("/")
        if normal == wanted or normal.startswith(wanted + "/"):
            return True
    return False


def _limit(task_value: int, data: GateInput, name: str) -> int:
    limits = data.values.get("limits")
    from_policy = limits.get(name) if isinstance(limits, dict) else None
    policy = from_policy if isinstance(from_policy, int) and from_policy > 0 else 0
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
        findings = [*self._forbidden(), *self._too_big(data), *self._undeclared()]
        return rejected(findings) if findings else Approved()

    def _forbidden(self) -> list[Finding]:
        findings = []
        seen: set[str] = set()
        for change in self.changes.files:
            for path in (change.old_path, change.path):
                if path is None or path in seen:
                    continue
                seen.add(path)
                kind = self.classify(path)
                if kind is not FileClass.PRODUCTION:
                    message = f"a {kind.value} file may not change in a refactoring"
                    findings.append(Finding(message=message, target=path))
                elif not in_scope(path, self.task.scope):
                    findings.append(Finding(message="outside the task scope", target=path))
        return findings

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
