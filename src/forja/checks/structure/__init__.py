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
from forja.checks.structure.nodes import Module, SyntaxProblem, no_declarations


@dataclass(frozen=True)
class Dialect:
    name: str
    language: str  # the name the policy and the adapters use for it
    suffixes: tuple[str, ...]
    grammar: Callable[[], object]
    read: Callable[[Node], Module]
    imports: Callable[[Node], tuple[str, ...]]
    types: Callable[[Node], tuple[int, int]]  # the abstract ones and all of them
    declared: Callable[[Node], tuple[str, ...]]  # package or namespaces; none for other languages


DIALECTS = (
    Dialect(
        "python",
        "python",
        (".py", ".pyi"),
        tree_sitter_python.language,
        python.read,
        python.imports,
        python.types,
        no_declarations,
    ),
    Dialect(
        "go",
        "go",
        (".go",),
        tree_sitter_go.language,
        go.read,
        go.imports,
        go.types,
        no_declarations,
    ),
    Dialect(
        "java",
        "java",
        (".java",),
        tree_sitter_java.language,
        java.read,
        java.imports,
        java.types,
        java.declared,
    ),
    Dialect(
        "csharp",
        "csharp",
        (".cs",),
        tree_sitter_c_sharp.language,
        csharp.read,
        csharp.imports,
        csharp.types,
        csharp.declared,
    ),
    Dialect(
        "javascript",
        "javascript",
        (".js", ".mjs", ".cjs", ".jsx"),
        tree_sitter_javascript.language,
        script.read,
        script.imports,
        script.types,
        no_declarations,
    ),
    Dialect(
        "typescript",
        "typescript",
        (".ts", ".mts", ".cts"),
        tree_sitter_typescript.language_typescript,
        script.read,
        script.imports,
        script.types,
        no_declarations,
    ),
    Dialect(
        "tsx",
        "typescript",
        (".tsx",),
        tree_sitter_typescript.language_tsx,
        script.read,
        script.imports,
        script.types,
        no_declarations,
    ),
)
SUFFIXES = tuple(suffix for dialect in DIALECTS for suffix in dialect.suffixes)

__all__ = [
    "DIALECTS",
    "SUFFIXES",
    "Dialect",
    "Module",
    "SyntaxProblem",
    "analyze",
    "dialect_of",
    "imports_of",
    "tree_of",
]


def dialect_of(path: str) -> Dialect | None:
    lowered = path.lower()
    return next((d for d in DIALECTS if lowered.endswith(d.suffixes)), None)


@cache
def _parser(name: str) -> Parser:
    dialect = next(d for d in DIALECTS if d.name == name)
    return Parser(Language(dialect.grammar()))


def tree_of(path: str, source: str) -> tuple[Dialect, Node] | None:
    """The dialect and syntax tree of ``source``, or ``None`` for a language Forja does not read.

    Raises ``SyntaxProblem`` when the text does not parse.
    """
    dialect = dialect_of(path)
    if dialect is None:
        return None
    root = _parser(dialect.name).parse(source.encode("utf-8")).root_node
    if root.has_error:
        raise SyntaxProblem(f"{path} does not parse as {dialect.name}")
    return dialect, root


def analyze(path: str, source: str) -> Module | None:
    """The shape of ``source``, or ``None`` for a language Forja does not read.

    Raises ``SyntaxProblem`` when the text does not parse.
    """
    tree = tree_of(path, source)
    return None if tree is None else tree[0].read(tree[1])


def imports_of(path: str, source: str) -> tuple[str, ...] | None:
    """What the file imports, as written, or ``None`` for a language Forja does not read.

    Raises ``SyntaxProblem`` when the text does not parse.
    """
    tree = tree_of(path, source)
    return None if tree is None else tree[0].imports(tree[1])
