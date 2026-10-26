"""What one production file says about the architecture, read once per distinct text."""

from dataclasses import dataclass
from functools import lru_cache

from forja.checks.structure import tree_of


@dataclass(frozen=True)
class FileFacts:
    imports: tuple[str, ...]  # as written, see ``forja.checks.structure``
    abstract: int  # the abstract types the file declares
    types: int  # all the types the file declares
    declared: tuple[str, ...]  # the package or namespaces; the Java package comes first


@lru_cache(maxsize=8192)
def read_file(path: str, source: str) -> FileFacts | None:
    """The facts of ``source``, or ``None`` for a language Forja does not read.

    Raises ``SyntaxProblem`` when the text does not parse.
    """
    tree = tree_of(path, source)
    if tree is None:
        return None
    dialect, root = tree
    abstract, types = dialect.types(root)
    return FileFacts(dialect.imports(root), abstract, types, dialect.declared(root))
