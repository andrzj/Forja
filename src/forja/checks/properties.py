"""Gate 6: an attempt that changes production code brings a property test (observation only).

The check looks for the property-testing library of the language in the test files the attempt
changed: Hypothesis for Python, fast-check for TypeScript, QuickTheories for Java, rapid for Go,
FsCheck for C#. It measures that a property test is there, never how
good it is, and it asks for one per language that had production code changed.
"""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from forja.checks.base import Undecided, decided, rejected
from forja.checks.changes import Changes
from forja.core.gates import (
    Approved,
    Finding,
    GateInput,
    GateResult,
    Inconclusive,
    InconclusiveReason,
)

READ_LIMIT = 1_000_000  # bytes read of a test file: the library is named near the top


@dataclass(frozen=True)
class Library:
    language: str
    needle: str  # what a test file that uses the library must contain


PYTHON = Library("python", "hypothesis")
TYPESCRIPT = Library("typescript", "fast-check")
JAVA = Library("java", "org.quicktheories")
GO = Library("go", "pgregory.net/rapid")
CSHARP = Library("csharp", "FsCheck")
LIBRARIES: dict[str, Library] = {
    **dict.fromkeys((".py", ".pyi"), PYTHON),
    **dict.fromkeys((".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs"), TYPESCRIPT),
    ".java": JAVA,
    ".go": GO,
    ".cs": CSHARP,
}


def library_of(path: str) -> Library | None:
    return LIBRARIES.get(Path(path).suffix.lower())


@dataclass(frozen=True)
class PropertiesCheck:
    worktree: Path
    changes: Changes
    production: tuple[str, ...]  # the production files the attempt changed
    is_test: Callable[[str], bool]  # a test or a fixture, as the language adapters class it
    id: str = "properties"
    gate: int = 6
    requires: frozenset[str] = frozenset()

    async def evaluate(self, data: GateInput) -> GateResult:
        return await decided(self._judge())

    async def _judge(self) -> GateResult:
        wanted: dict[Library, str] = {}  # the library, and the first production file that wants it
        for path in self.production:
            if (library := library_of(path)) is not None:
                wanted.setdefault(library, path)
        if not wanted:
            return Approved()
        used: set[Library] = set()
        unreadable: dict[Library, list[str]] = {}  # per language: a lack is unknown only there
        for path in self.changes.current(self.is_test):
            library = library_of(path)
            if library is None or library in used:
                continue
            try:
                where = self.worktree / path
                if where.is_symlink() or where.is_junction():
                    continue  # a link may lead out of the worktree; it counts for nothing
                with where.open("rb") as handle:
                    text = handle.read(READ_LIMIT).decode("utf-8", errors="replace")
            except OSError:  # what is in it is unknown, so it is never taken for a lack
                unreadable.setdefault(library, []).append(path)
                continue
            if library.needle in text:
                used.add(library)
        findings = [
            Finding(
                message=f"no {library.language} property test ({library.needle}) in changed tests",
                target=path,
                measured=0,
                limit=1,
            )
            for library, path in wanted.items()
            if library not in used
        ]
        unknown = [
            path
            for library in wanted
            if library not in used
            for path in unreadable.get(library, ())
        ]
        if unknown:
            raise Undecided(
                Inconclusive(
                    reason=InconclusiveReason.TOOL_FAILED,
                    detail="properties: cannot read " + ", ".join(unknown[:3]),
                )
            )
        return rejected(findings) if findings else Approved()
