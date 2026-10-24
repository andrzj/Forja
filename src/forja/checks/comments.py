"""Gate 12: the comments an attempt adds say something the code does not, and the public interface
it adds has a comment.

Two of Ousterhout's rules, in observation by default. A comment repeats the code when nearly all
its words are words of the line it sits on or above (identifiers split at camel case and
underscores): it tells the reader nothing the line did not. A public symbol the attempt creates
with no comment above it (or no docstring, in Python) leaves the reader to read the body. Only new
comments and new symbols count, so old code is never blamed.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from tree_sitter import Node

from forja.checks.base import decided, rejected
from forja.checks.changes import Changes, added_lines
from forja.checks.structure import SyntaxProblem, tree_of
from forja.checks.structure.nodes import COMMENTS, text, walk
from forja.checks.symbols import symbols_in
from forja.core.adapters import FileClass
from forja.core.gates import Approved, Finding, GateInput, GateResult, Location

MIN_WORDS = 2  # a comment of one word (``noqa``, ``TODO``) is a label, not a sentence
REPEAT_RATIO = 0.75  # the share of the comment's words that the code already has
# words of three letters or more that carry no meaning of their own (shorter ones are dropped)
STOP = frozenset(
    {
        "the", "and", "for", "with", "that", "this", "from", "are", "was", "were", "has", "have",
        "into", "its", "onto", "over", "per", "via", "then", "than", "not", "but", "can", "will",
        "may", "all", "any", "each", "some", "one", "out", "off", "too",
        "dos", "das", "uma", "uns", "umas", "para", "por", "com", "sem", "que", "como", "mais",
        "aos", "nas", "nos",
    }
)  # fmt: skip
_WORD = re.compile(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|\d+")
_DELIMITERS = re.compile(r"^\s*(?:///?|/\*+|\*+/?|#+|--|;;?)\s?|\s*\*/\s*$")


def words(source: str) -> frozenset[str]:
    """The lower-case words of ``source``, identifiers split at camel case and underscores."""
    found = (w.lower() for w in _WORD.findall(source.replace("_", " ")))
    return frozenset(w for w in found if len(w) > 2 and w not in STOP and not w.isdigit())


def repeats(comment: str, code: str) -> bool:
    """Whether the comment only says again what the code line says."""
    said = words(_DELIMITERS.sub("", comment))
    if len(said) < MIN_WORDS:
        return False
    return len(said & words(code)) / len(said) >= REPEAT_RATIO


def _target(comment: Node) -> str:
    """The code a comment is about: the line it ends, or the declaration right below it."""
    before = comment.prev_sibling
    if (
        before is not None
        and before.type not in COMMENTS
        and before.end_point[0] == comment.start_point[0]
    ):
        return text(before)
    below = comment.next_named_sibling
    while below is not None and below.type in COMMENTS:
        below = below.next_named_sibling
    if below is None or below.start_point[0] > comment.end_point[0] + 1:
        return ""
    return text(below).split("\n", 1)[0]  # the header: a body would share words with anything


@dataclass(frozen=True)
class CommentsCheck:
    worktree: Path
    changes: Changes
    before: dict[str, str]  # the parent commit's text of the changed files, by old path
    classify: Callable[[str], FileClass]
    id: str = "comments"
    gate: int = 12
    requires: frozenset[str] = frozenset()

    async def evaluate(self, data: GateInput) -> GateResult:
        return await decided(self._judge())

    async def _judge(self) -> GateResult:
        added: dict[str, set[int]] = {}
        for line in added_lines(self.changes.patch):
            if line.path is not None and line.number is not None:
                added.setdefault(line.path, set()).add(line.number)
        findings: list[Finding] = []
        for change in self.changes.files:
            if not change.exists_now:
                continue
            try:
                source = (self.worktree / change.path).read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            findings += self._repeated(change.path, source, added.get(change.path, set()))
            if self.classify(change.path) is FileClass.PRODUCTION:
                findings += self._undocumented(change.path, change.before, source)
        return rejected(findings) if findings else Approved()

    @staticmethod
    def _repeated(path: str, source: str, numbers: set[int]) -> list[Finding]:
        try:
            tree = tree_of(path, source)
        except SyntaxProblem:
            return []
        if tree is None:
            return []
        found = []
        for node in walk(tree[1]):
            if node.type not in COMMENTS:
                continue
            rows = set(range(node.start_point[0] + 1, node.end_point[0] + 2))
            if rows <= numbers and repeats(text(node), _target(node)):
                found.append(_finding("a comment repeats the code next to it", path, min(rows)))
        return found

    def _undocumented(self, path: str, old_path: str | None, source: str) -> list[Finding]:
        now = symbols_in(path, source)
        if now is None:
            return []
        was = symbols_in(old_path, self.before[old_path]) if old_path in self.before else ()
        known = {symbol.name for symbol in was or ()}
        return [
            _finding(
                f"the new public {symbol.kind} {symbol.name} has no comment", path, symbol.line
            )
            for symbol in now
            if symbol.public and not symbol.documented and symbol.name not in known
        ]


def _finding(message: str, path: str, line: int) -> Finding:
    return Finding(message=message, target=path, location=Location(path=path, line=line))
