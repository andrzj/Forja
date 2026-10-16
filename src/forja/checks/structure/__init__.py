"""Readers of a source file's shape (pass-through functions, size of surface) for every language.

One tree-sitter grammar per language; the readers differ only in the names of the nodes.
"""

from collections.abc import Callable
from dataclasses import dataclass
from functools import cache

import tree_sitter_c_sharp
import tree_sitter_go
import tree_sitter_java
import tree_sitter_javascript
import tree_sitter_python
import tree_sitter_typescript
from tree_sitter import Language, Node, Parser

from forja.checks.structure import csharp, go, java, python, script
from forja.checks.structure.nodes import Module, SyntaxProblem


@dataclass(frozen=True)
class Dialect:
    name: str
    language: str  # the name the policy and the adapters use for it
    suffixes: tuple[str, ...]
    grammar: Callable[[], object]
    read: Callable[[Node], Module]


DIALECTS = (
    Dialect("python", "python", (".py", ".pyi"), tree_sitter_python.language, python.read),
    Dialect("go", "go", (".go",), tree_sitter_go.language, go.read),
    Dialect("java", "java", (".java",), tree_sitter_java.language, java.read),
    Dialect("csharp", "csharp", (".cs",), tree_sitter_c_sharp.language, csharp.read),
    Dialect(
        "javascript",
        "javascript",
        (".js", ".mjs", ".cjs", ".jsx"),
        tree_sitter_javascript.language,
        script.read,
    ),
    Dialect(
        "typescript",
        "typescript",
        (".ts", ".mts", ".cts"),
        tree_sitter_typescript.language_typescript,
        script.read,
    ),
    Dialect("tsx", "typescript", (".tsx",), tree_sitter_typescript.language_tsx, script.read),
)
SUFFIXES = tuple(suffix for dialect in DIALECTS for suffix in dialect.suffixes)

__all__ = ["DIALECTS", "SUFFIXES", "Dialect", "Module", "SyntaxProblem", "analyze", "dialect_of"]


def dialect_of(path: str) -> Dialect | None:
    lowered = path.lower()
    return next((d for d in DIALECTS if lowered.endswith(d.suffixes)), None)


@cache
def _parser(name: str) -> Parser:
    dialect = next(d for d in DIALECTS if d.name == name)
    return Parser(Language(dialect.grammar()))


def analyze(path: str, source: str) -> Module | None:
    """The shape of ``source``, or ``None`` for a language Forja does not read.

    Raises ``SyntaxProblem`` when the text does not parse.
    """
    dialect = dialect_of(path)
    if dialect is None:
        return None
    root = _parser(dialect.name).parse(source.encode("utf-8")).root_node
    if root.has_error:
        raise SyntaxProblem(f"{path} does not parse as {dialect.name}")
    return dialect.read(root)
