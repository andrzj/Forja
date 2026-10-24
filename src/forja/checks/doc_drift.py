"""Documents that cite what is no longer there: a path, a command or a symbol (gate 14).

Only what sits between backticks is read, outside fenced blocks, so a document says what it means
to be checked. A path must be in the repository; ``make target`` and ``npm run script`` must name
a target or a script that is declared; a symbol (a name that looks like code, with ``()``, an
underscore, a dot or mixed case) must be a word in some file that is not documentation. A symbol
is looked for as text, as a reference to it would be: a constant or a configuration key counts,
a homonym hides a removal.
"""

import json
import posixpath
import re
from collections.abc import Iterable
from dataclasses import dataclass

PATH, COMMAND, SYMBOL = "path", "command", "symbol"
EXTENSIONS = frozenset(
    {
        *("md", "rst", "toml", "json", "yaml", "yml", "py", "go", "java", "cs", "js", "ts"),
        *("tsx", "jsx", "sh", "ps1", "txt", "cfg", "ini", "lock", "gradle", "xml", "sql"),
    }
)
LAUNCHERS = frozenset({"npm", "yarn", "pnpm", "bun"})
_FENCE = re.compile(r"^\s*(```+|~~~+)")
_SPAN = re.compile(r"`([^`\n]+)`")
_WORD = re.compile(r"[A-Za-z_]\w*")
_SYMBOL = re.compile(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*(?:\(\))?")
_LINE_SUFFIX = re.compile(r":\d+(?:-\d+)?$")
_NOT_A_PATH = re.compile(r"[\s*?<>{}$|;&=\"']|://|^[-~@#]")
_TARGET = re.compile(r"^([^\s:=#\t.][^:=#\n]*?)\s*:(?![=:])", re.MULTILINE)


@dataclass(frozen=True)
class Reference:
    document: str
    line: int
    kind: str
    token: str  # the path, ``make target``, or the symbol as the document spells it
    span: str  # what is between the backticks


@dataclass(frozen=True)
class Facts:
    """What the repository has, as a document can cite it."""

    files: frozenset[str]
    words: frozenset[str]  # the identifiers in the files that are not documentation
    make_targets: frozenset[str] = frozenset()
    scripts: frozenset[str] = frozenset()

    def directories(self) -> frozenset[str]:
        return frozenset(parent for path in self.files for parent in _parents(path))


def _parents(path: str) -> Iterable[str]:
    folder = posixpath.dirname(path)
    while folder:
        yield folder
        folder = posixpath.dirname(folder)


def words_in(text: str) -> set[str]:
    return set(_WORD.findall(text))


def make_targets(text: str) -> set[str]:
    """The targets a Makefile declares: every name before the colon of a rule."""
    return {name for match in _TARGET.findall(text) for name in match.split()}


def package_scripts(text: str) -> set[str]:
    """The script names of a ``package.json``; none for text that is not one."""
    try:
        found = json.loads(text)
    except ValueError:
        return set()
    scripts = found.get("scripts") if isinstance(found, dict) else None
    return (
        {name for name in scripts if isinstance(name, str)} if isinstance(scripts, dict) else set()
    )


def references(document: str, text: str) -> list[Reference]:
    """What the document cites between backticks, outside fenced blocks."""
    found: list[Reference] = []
    fenced = ""
    for number, line in enumerate(text.split("\n"), start=1):
        fence = _FENCE.match(line)
        if fence:
            marker = fence.group(1)[0]
            fenced = "" if fenced == marker else fenced or marker
        elif not fenced:
            for span in _SPAN.findall(line):
                reference = _classify(document, number, span.strip())
                if reference is not None:
                    found.append(reference)
    return found


def _classify(document: str, line: int, span: str) -> Reference | None:
    command = _command(span)
    if command is not None:
        return Reference(document, line, COMMAND, command, span)
    path = _LINE_SUFFIX.sub("", span)
    if _is_path(path):
        return Reference(document, line, PATH, path, span)
    if _is_symbol(span):
        return Reference(document, line, SYMBOL, span.removesuffix("()"), span)
    return None


def _command(span: str) -> str | None:
    """``make target`` or ``npm run script``, as the target or script they name."""
    words = span.split()
    if len(words) >= 2 and words[0] == "make":
        target = next((w for w in words[1:] if not w.startswith("-") and "=" not in w), None)
        return f"make {target}" if target else None
    if len(words) >= 3 and words[0] in LAUNCHERS and words[1] in ("run", "run-script"):
        return f"{words[0]} run {words[2]}" if not words[2].startswith("-") else None
    return None


def _is_path(text: str) -> bool:
    if not text or _NOT_A_PATH.search(text) or text.startswith(("/", "\\")) or ":" in text:
        return False
    text = text.replace("\\", "/")
    if "/" in text:
        return True
    name, dot, extension = text.rpartition(".")
    return bool(name) and bool(dot) and extension.lower() in EXTENSIONS


def _is_symbol(span: str) -> bool:
    if not _SYMBOL.fullmatch(span):
        return False
    name = span.removesuffix("()")
    if span.endswith("()") or "_" in name or "." in name:
        return True
    return any(c.islower() for c in name) and any(c.isupper() for c in name)


def candidates(reference: Reference) -> list[str]:
    """The places a path may mean, the repository first and the document's folder second; empty
    for a path that leaves the repository."""
    path = reference.token.replace("\\", "/")
    places = [path, posixpath.join(posixpath.dirname(reference.document), path)]
    found = []
    for place in places:
        normal = posixpath.normpath(place)
        if normal.startswith("..") or normal == "." or normal.startswith("/"):
            continue
        if normal not in found:
            found.append(normal)
    return found


def missing(reference: Reference, facts: Facts) -> list[str]:
    """What the reference names that the repository does not have; empty when it is all there."""
    if reference.kind == PATH:
        places = candidates(reference)
        known = facts.files | facts.directories()
        return [] if not places or any(place in known for place in places) else [reference.token]
    if reference.kind == COMMAND:
        program, _, target = reference.token.rpartition(" ")
        names = facts.make_targets if program == "make" else facts.scripts
        return [] if target in names else [target]
    return [part for part in reference.token.split(".") if part not in facts.words]


def drift(documents: dict[str, str], facts: Facts) -> list[tuple[Reference, list[str]]]:
    """Every citation of the documents that has no counterpart, with what is not there."""
    found = []
    for document, text in documents.items():
        for reference in references(document, text):
            gone = missing(reference, facts)
            if gone:
                found.append((reference, gone))
    return found
