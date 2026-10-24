"""Gate 14: the README after the documenter, against the README before it.

The model may fix the sections that failed and nothing else; what the Forja checks is that a
section that was fine is byte for byte what it was, and says what is still wrong afterwards.
"""

from dataclasses import dataclass
from pathlib import Path

from forja.checks.base import decided, rejected
from forja.checks.readme import README_NAMES, Signature, evaluate, touched_chunks
from forja.core.gates import Approved, Finding, GateInput, GateResult


def readme_path(worktree: Path) -> str | None:
    """The README at the root of the worktree, ``None`` if there is none."""
    return next((name for name in README_NAMES if (worktree / name).is_file()), None)


def read_readme(worktree: Path) -> tuple[str | None, str | None]:
    """The name and the text of the README, or ``(None, None)``; an unreadable one is no README."""
    name = readme_path(worktree)
    if name is None:
        return None, None
    try:
        return name, (worktree / name).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None, None


@dataclass(frozen=True)
class ReadmeCheck:
    worktree: Path
    old: str | None  # the README as the documenter's stage began; ``None``: there was none
    build: frozenset[Signature]
    test: frozenset[Signature]
    id: str = "readme"
    gate: int = 14
    requires: frozenset[str] = frozenset()

    async def evaluate(self, data: GateInput) -> GateResult:
        return await decided(self._judge())

    async def _judge(self) -> GateResult:
        name, new = read_readme(self.worktree)
        target = name or README_NAMES[0]

        def exists(relative: str) -> bool:
            return (self.worktree / relative).exists()

        findings = []
        if self.old is not None and new is not None:
            before = evaluate(self.old, exists, self.build, self.test)
            findings += [
                Finding(
                    message=f"the README section {heading!r} had no problem and changed",
                    target=target,
                )
                for heading in touched_chunks(self.old, new, before)
            ]
        findings += [
            Finding(message=f"README: {problem.message}", target=target)
            for problem in evaluate(new, exists, self.build, self.test)
        ]
        return rejected(findings) if findings else Approved()
