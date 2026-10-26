"""JavaScript and TypeScript: pass-through functions and the size of the exported surface."""

from tree_sitter import Node

from forja.checks.structure.nodes import (
    Module,
    count_statements,
    field,
    forwards,
    kids,
    sole,
    text,
    walk,
)

_STATEMENTS = frozenset(
    {
        "function_declaration",
        "class_declaration",
        "abstract_class_declaration",
        "lexical_declaration",
        "variable_declaration",
        "method_definition",
        "interface_declaration",
        "type_alias_declaration",
        "enum_declaration",
    }
)
_SKIP = frozenset({"export_statement", "import_statement"})
_WRAPPERS = frozenset({"return_statement", "expression_statement"})
_CLASSES = frozenset({"class_declaration", "abstract_class_declaration"})
_FUNCTION_VALUES = frozenset({"arrow_function", "function_expression", "function"})
_HIDDEN = frozenset({"private", "protected"})


def read(root: Node) -> Module:
    found: set[str] = set()
    _walk(root, (), found)
    return Module(frozenset(found), _interface(root), count_statements(root, _STATEMENTS, _SKIP))


def _walk(node: Node, scope: tuple[str, ...], found: set[str]) -> None:
    for child in kids(node):
        name = text(field(child, "name"))
        if child.type in _CLASSES:
            _walk(child, (*scope, name), found)
            continue
        if child.type == "variable_declarator":
            value = field(child, "value")
            if value is not None and value.type in _FUNCTION_VALUES:
                _check(value, ".".join((*scope, name)), found)
        elif child.type == "function_declaration" or (
            child.type == "method_definition" and name != "constructor"
        ):
            _check(child, ".".join((*scope, name)), found)
        _walk(child, scope, found)


def _check(function: Node, qualified: str, found: set[str]) -> None:
    if _forwards(function):
        found.add(qualified)


def _forwards(function: Node) -> bool:
    body = field(function, "body")
    if body is None:
        return False
    call = sole(kids(body), _WRAPPERS) if body.type == "statement_block" else body
    if call is None or call.type != "call_expression":
        return False
    arguments = field(call, "arguments")
    if arguments is None:
        return False
    return forwards(_params(function), [_arg(a) for a in kids(arguments)])


def _params(function: Node) -> list[str | None]:
    parameters = field(function, "parameters")
    return [_param(p) for p in (kids(parameters) if parameters is not None else [])]


def _param(node: Node) -> str | None:
    if node.type in ("required_parameter", "optional_parameter"):
        pattern = field(node, "pattern")
        return _param(pattern) if pattern is not None else None
    if node.type == "assignment_pattern":
        left = field(node, "left")
        return _param(left) if left is not None else None
    if node.type == "rest_pattern":
        return "*" + text(kids(node)[0]) if kids(node) else None
    return text(node) if node.type == "identifier" else None


def _arg(node: Node) -> str | None:
    if node.type == "identifier":
        return text(node)
    if node.type == "spread_element" and kids(node):
        return "*" + text(kids(node)[0])
    return None


def _weight(function: Node) -> int:
    return 1 + len([p for p in _params(function) if p is not None])


def _interface(root: Node) -> int:
    size = 0
    for child in kids(root):
        if child.type != "export_statement":
            continue
        declaration = field(child, "declaration")
        if declaration is None:  # `export { a, b }` names things declared elsewhere
            size += sum(
                len(kids(clause)) for clause in kids(child) if clause.type == "export_clause"
            )
        else:
            size += _exported(declaration)
    return size


def _exported(node: Node) -> int:
    if node.type == "function_declaration":
        return _weight(node)
    if node.type in _CLASSES:
        return 1 + _members(node)
    if node.type == "lexical_declaration":
        size = 0
        for declarator in kids(node):
            value = field(declarator, "value")
            size += _weight(value) if value is not None and value.type in _FUNCTION_VALUES else 1
        return size
    if node.type == "interface_declaration":
        body = field(node, "body")
        return 1 + sum(
            _weight(m) if m.type == "method_signature" else 1
            for m in (kids(body) if body is not None else [])
        )
    return 1  # a type alias, an enum


def _members(cls: Node) -> int:
    body = field(cls, "body")
    size = 0
    for member in kids(body) if body is not None else []:
        name = text(field(member, "name"))
        hidden = any(
            k.type == "accessibility_modifier" and text(k) in _HIDDEN for k in kids(member)
        )
        if member.type == "method_definition" and not (hidden or name.startswith(("#", "_"))):
            size += _weight(member)
    return size


_LOADERS = frozenset({"import", "require"})


def imports(root: Node) -> tuple[str, ...]:
    """The specifier of each import, re-export, ``import()`` and ``require()`` naming a literal.

    A call whose argument is not a plain string is a path only the running program knows, so it
    is left out.
    """
    found: list[str] = []
    for node in walk(root):
        if node.type in {"import_statement", "export_statement"}:
            source = field(node, "source")
            if source is not None:
                found.append(_specifier(source))
        elif node.type == "import_require_clause":
            found.extend(_specifier(c) for c in kids(node) if c.type == "string")
        elif node.type == "call_expression" and text(field(node, "function")) in _LOADERS:
            call = field(node, "arguments")
            arguments = kids(call) if call is not None else []
            if len(arguments) == 1 and arguments[0].type == "string":
                found.append(_specifier(arguments[0]))
    return tuple(s for s in found if s)


def _specifier(node: Node) -> str:
    return "".join(text(c) for c in node.children if c.type == "string_fragment")


_TYPE_DECLARATIONS = frozenset(
    {"class_declaration", "abstract_class_declaration", "interface_declaration", "enum_declaration"}
)
_ABSTRACT_DECLARATIONS = frozenset({"abstract_class_declaration", "interface_declaration"})


def types(root: Node) -> tuple[int, int]:
    """The interfaces and abstract classes, and all the types; plain JavaScript has no abstract."""
    found = [n for n in walk(root) if n.type in _TYPE_DECLARATIONS]
    return sum(1 for n in found if n.type in _ABSTRACT_DECLARATIONS), len(found)
