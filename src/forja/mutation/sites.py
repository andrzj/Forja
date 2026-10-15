"""Find the mutation sites of a Python file.

The operators and the way a change is worded follow unclebob/mutator (which reads Python with
tree-sitter): an operator is changed only inside an arithmetic, comparison or boolean expression,
``not`` and a unary ``-`` are deleted, ``True`` and ``False`` swap, and of the numbers only ``0``
and ``1`` swap. Strings and comments hold no site, and neither does code outside a function.

``ast`` gives the position of an expression, not of its operator. The operator is the token of
that text found between the two operands (what lies there besides it is parentheses).
"""

import ast
import tokenize
from bisect import bisect_left
from collections.abc import Iterator
from typing import NamedTuple

from forja.mutation.model import Site

Position = tuple[int, int]  # (line, byte column)
Change = tuple[str, str, str]  # original, mutant, category

_ARITHMETIC: dict[type[ast.operator], Change] = {
    ast.Add: ("+", "-", "arithmetic"),
    ast.Sub: ("-", "+", "arithmetic"),
    ast.Mult: ("*", "/", "arithmetic"),
    ast.Div: ("/", "*", "arithmetic"),
}
_COMPARISON: dict[type[ast.cmpop], Change] = {
    ast.Lt: ("<", "<=", "comparison"),
    ast.LtE: ("<=", "<", "comparison"),
    ast.Gt: (">", ">=", "comparison"),
    ast.GtE: (">=", ">", "comparison"),
    ast.Eq: ("==", "!=", "equality"),
    ast.NotEq: ("!=", "==", "equality"),
    ast.NotIn: ("not", "", "unary"),  # `a not in b` loses its `not`; the `in` stays
    ast.IsNot: ("not", "", "unary"),
}
_LOGICAL: dict[type[ast.boolop], Change] = {
    ast.And: ("and", "or", "logical"),
    ast.Or: ("or", "and", "logical"),
}
_UNARY: dict[type[ast.unaryop], Change] = {
    ast.Not: ("not", "", "unary"),
    ast.USub: ("-", "", "unary"),
}
_WORDS = {
    original
    for table in (_ARITHMETIC, _COMPARISON, _LOGICAL, _UNARY)
    for original, _, _ in table.values()
}


class _Token(NamedTuple):
    start: Position
    end: Position
    text: str


def _start(node: ast.expr) -> Position:
    return (node.lineno, node.col_offset)


def _end(node: ast.expr) -> Position:
    return (node.end_lineno or node.lineno, node.end_col_offset or node.col_offset)


class _Source:
    """The file as bytes, with the tokens that can be an operator and their byte positions."""

    def __init__(self, source: str) -> None:
        lines = source.splitlines(keepends=True)
        self.data = source.encode("utf-8")
        self._line_starts = [0]
        for line in lines:
            self._line_starts.append(self._line_starts[-1] + len(line.encode("utf-8")))
        self._tokens = list(self._operator_tokens(lines))
        self._starts = [token.start for token in self._tokens]

    @staticmethod
    def _operator_tokens(lines: list[str]) -> Iterator[_Token]:
        feed = iter(lines)
        for token in tokenize.generate_tokens(lambda: next(feed, "")):
            if token.string in _WORDS:
                yield _Token(
                    _byte_position(lines, token.start),
                    _byte_position(lines, token.end),
                    token.string,
                )

    def offset(self, position: Position) -> int:
        return self._line_starts[position[0] - 1] + position[1]

    def between(self, first_end: Position, second_start: Position, text: str) -> _Token | None:
        """The token ``text`` that lies between two operands, if there is one."""
        index = bisect_left(self._starts, first_end)
        while index < len(self._tokens) and self._tokens[index].end <= second_start:
            if self._tokens[index].text == text:
                return self._tokens[index]
            index += 1
        return None


def _byte_position(lines: list[str], position: Position) -> Position:
    row, column = position
    line = lines[row - 1] if row <= len(lines) else ""
    return (row, len(line[:column].encode("utf-8")))


class _Collector:
    def __init__(self, source: str) -> None:
        self._source = _Source(source)
        self.found: list[Site] = []

    def visit(self, node: ast.AST, function: str) -> None:
        match node:
            case ast.BinOp(left=left, op=op, right=right):
                self._operator(_ARITHMETIC.get(type(op)), left, right, function)
            case ast.Compare():
                self._compare(node, function)
            case ast.BoolOp():
                self._logical(node, function)
            case ast.UnaryOp(op=op):
                self._unary(node, _UNARY.get(type(op)), function)
            case ast.Constant(value=value):
                self._constant(node, value, function)

    def _operator(
        self, change: Change | None, left: ast.expr, right: ast.expr, function: str
    ) -> None:
        if change is not None:
            self._between(_end(left), _start(right), change, function)

    def _between(
        self, first_end: Position, second_start: Position, change: Change, function: str
    ) -> None:
        token = self._source.between(first_end, second_start, change[0])
        if token is not None:
            self._add(token.start, token.end, change, function)

    def _compare(self, node: ast.Compare, function: str) -> None:
        operands = [node.left, *node.comparators]
        for index, op in enumerate(node.ops):
            change = _COMPARISON.get(type(op))
            if change is not None:
                self._between(_end(operands[index]), _start(operands[index + 1]), change, function)

    def _logical(self, node: ast.BoolOp, function: str) -> None:
        change = _LOGICAL.get(type(node.op))
        for left, right in zip(node.values, node.values[1:], strict=False):
            self._operator(change, left, right, function)

    def _unary(self, node: ast.UnaryOp, change: Change | None, function: str) -> None:
        if change is None:
            return
        token = self._source.between(_start(node), _end(node), change[0])
        if token is not None and token.start == _start(node):
            self._add(token.start, token.end, change, function)

    def _constant(self, node: ast.Constant, value: object, function: str) -> None:
        start, end = _start(node), _end(node)
        if isinstance(value, bool):
            original = "True" if value else "False"
            self._add(start, end, (original, str(not value), "boolean"), function)
        elif type(value) is int and value in (0, 1):
            original = str(value)  # `0x1`, `1_0` and `00` are other texts of the same value
            if (
                self._source.data[self._source.offset(start) : self._source.offset(end)]
                == original.encode()
            ):
                self._add(start, end, (original, str(1 - value), "constant"), function)

    def _add(self, start: Position, end: Position, change: Change, function: str) -> None:
        original, mutant, category = change
        self.found.append(
            Site(
                line=start[0],
                start=self._source.offset(start),
                end=self._source.offset(end),
                original=original,
                mutant=mutant,
                category=category,
                function=function,
            )
        )


def _owned(tree: ast.AST) -> Iterator[tuple[ast.AST, str]]:
    """Every node with the qualified name of the innermost ``def`` that holds it.

    Code outside a function (module level, a class body) has no owner and is left out. The
    decorators of a function are outside it; its parameters, defaults and annotations are inside.
    """
    stack: list[tuple[ast.AST, str, str]] = [(tree, "", "")]  # node, name prefix, owner
    while stack:
        node, prefix, owner = stack.pop()
        if owner:
            yield node, owner
        stack.extend(_children(node, prefix, owner))


def _children(node: ast.AST, prefix: str, owner: str) -> Iterator[tuple[ast.AST, str, str]]:
    if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
        name = f"{prefix}{node.name}"
        decorators = [id(decorator) for decorator in node.decorator_list]
        for child in ast.iter_child_nodes(node):
            outside = id(child) in decorators
            yield (child, prefix, owner) if outside else (child, f"{name}.", name)
    elif isinstance(node, ast.ClassDef):
        for child in ast.iter_child_nodes(node):
            yield child, f"{prefix}{node.name}.", owner
    else:
        for child in ast.iter_child_nodes(node):
            yield child, prefix, owner


def discover(source: str) -> list[Site]:
    """The sites of ``source`` in file order. Raises ``SyntaxError`` if it is not Python."""
    tree = ast.parse(source)
    collector = _Collector(source)
    for node, function in _owned(tree):
        collector.visit(node, function)
    return sorted(collector.found, key=lambda site: (site.line, site.start, site.end))
