"""Gate 14: the documents cite nothing that is gone, and the drift the task did not cause is left.

The ratchet (as in the other gates) rejects only new drift. A citation is old when the document
had it at the base of the task and what it names was already missing then; anything else, a claim
the documenter just wrote or a name the task removed, is new.
"""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from forja.checks.base import decided, rejected
from forja.checks.changes import Git
from forja.checks.doc_drift import (
    COMMAND,
    PATH,
    Facts,
    Reference,
    candidates,
    drift,
    make_targets,
    package_scripts,
    words_in,
)
from forja.core.gates import Approved, Finding, GateInput, GateResult

MAX_TEXT_BYTES = 1_000_000  # a file bigger than this is data, not code to cite


def _text_of(path: Path) -> str | None:
    try:
        if path.stat().st_size > MAX_TEXT_BYTES:
            return None
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _is_plain_file(path: Path) -> bool:
    return path.is_file() and not path.is_symlink()


async def read_repository(
    git: Git, worktree: Path, is_document: Callable[[str], bool], records: str
) -> tuple[dict[str, str], Facts]:
    """The documents that can drift (the task's own records are history, not claims) and what the
    rest of the worktree has for them to cite; files the worktree does not hold are skipped."""
    listed = await git.lines("ls-files", "--cached", "--others", "--exclude-standard")
    files = frozenset(path for path in listed if _is_plain_file(worktree / path))
    prefix = records.rstrip("/") + "/"
    documents: dict[str, str] = {}
    words: set[str] = set()
    targets: set[str] = set()
    scripts: set[str] = set()
    for path in sorted(files):
        text = _text_of(worktree / path)
        if text is None:
            continue
        if is_document(path):
            if not path.startswith(prefix):
                documents[path] = text
            continue
        words |= words_in(text)
        name = path.rsplit("/", 1)[-1]
        if name in ("Makefile", "makefile", "GNUmakefile"):
            targets |= make_targets(text)
        elif name == "package.json":
            scripts |= package_scripts(text)
    return documents, Facts(files, frozenset(words), frozenset(targets), frozenset(scripts))


@dataclass
class Base:
    """The task's base commit, asked only about what the documents cite and no longer find."""

    git: Git
    commit: str
    head: str = "HEAD"

    def __post_init__(self) -> None:
        self._documents: dict[str, str] = {}

    async def _document(self, path: str) -> str:
        if path not in self._documents:
            listed = await self.git.lines("ls-tree", "--name-only", self.commit, "--", path)
            shown = await self.git.lines("show", f"{self.commit}:{path}") if listed else []
            self._documents[path] = "\n".join(shown)
        return self._documents[path]

    async def _had(self, place: str) -> bool:
        return bool(await self.git.lines("ls-tree", "--name-only", self.commit, "--", place))

    async def _touched(self, word: str) -> bool:
        """Whether a commit of the task added or removed ``word`` somewhere."""
        found = await self.git.lines(
            "log", "--format=%H", f"-S{word}", f"{self.commit}..{self.head}"
        )
        return bool(found)

    async def tolerates(self, reference: Reference, gone: list[str]) -> bool:
        """Whether the citation was there at the base and already pointed at nothing."""
        if f"`{reference.span}`" not in await self._document(reference.document):
            return False
        if reference.kind == PATH:
            return not any([await self._had(place.rstrip("/")) for place in candidates(reference)])
        return not any([await self._touched(word) for word in gone])


@dataclass(frozen=True)
class DocDriftCheck:
    documents: dict[str, str]
    facts: Facts
    base: Base
    id: str = "doc_drift"
    gate: int = 14
    requires: frozenset[str] = frozenset()

    async def evaluate(self, data: GateInput) -> GateResult:
        return await decided(self._judge())

    async def _judge(self) -> GateResult:
        findings = []
        for reference, gone in drift(self.documents, self.facts):
            if await self.base.tolerates(reference, gone):
                continue
            what = "command" if reference.kind == COMMAND else reference.kind
            findings.append(
                Finding(
                    message=(
                        f"line {reference.line} cites {what} `{reference.span}` and "
                        f"{', '.join(gone)} is gone"
                    ),
                    target=reference.document,
                )
            )
        return rejected(findings) if findings else Approved()
