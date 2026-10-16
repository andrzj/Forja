"""What every language reader shares: the result type and small helpers over tree-sitter nodes."""

from collections.abc import Iterator
from dataclasses import dataclass

from tree_sitter import Node

COMMENTS = frozenset({"comment", "line_comment", "block_comment"})


class SyntaxProblem(Exception):
    """The text does not parse, so nothing can be said about its structure."""


@dataclass(frozen=True)
class Module:
    """What one source file shows about its shape."""

    forwarders: frozenset[str]  # qualified names of the functions that only pass arguments on
    interface: int  # the size of the public surface: one per public name plus one per parameter
    statements: int  # the size of the implementation

    @property
    def ratio(self) -> float:
        return self.interface / self.statements if self.statements else 0.0


def kids(node: Node) -> list[Node]:
    """The named children, without comments."""
    return [child for child in node.named_children if child.type not in COMMENTS]


def text(node: Node | None) -> str:
    return node.text.decode("utf-8", "replace") if node is not None and node.text else ""


def field(node: Node, name: str) -> Node | None:
    return node.child_by_field_name(name)


def walk(node: Node) -> Iterator[Node]:
    pending = [node]
    while pending:
        current = pending.pop()
        yield current
        pending.extend(reversed(current.children))


def count_statements(root: Node, extra: frozenset[str], skip: frozenset[str] = frozenset()) -> int:
    """Nodes that are statements: every ``*_statement`` plus the declarations in ``extra``."""
    return sum(
        1
        for node in walk(root)
        if node.is_named
        and node.type not in skip
        and (node.type in extra or node.type.endswith("_statement"))
    )


def forwards(params: list[str | None], args: list[str | None] | None) -> bool:
    """The call hands on exactly the parameters, in order, and nothing else."""
    return args is not None and None not in params and None not in args and params == args


def sole(statements: list[Node], kinds: frozenset[str]) -> Node | None:
    """The one expression a body of a single statement holds, or ``None``.

    ``kinds`` are the statement types that wrap an expression (a return or a bare expression).
    """
    if len(statements) != 1 or statements[0].type not in kinds:
        return None
    inner = kids(statements[0])
    return inner[0] if len(inner) == 1 else None
