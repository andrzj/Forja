"""Python: pass-through functions and the size of the public surface."""

import re

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

_STATEMENTS = frozenset({"function_definition", "class_definition"})
_IMPORTS = frozenset({"import_statement", "import_from_statement", "future_import_statement"})
_WRAPPERS = frozenset({"return_statement", "expression_statement"})
_SELF = ("self", "cls")


def read(root: Node) -> Module:
    found: set[str] = set()
    _walk(root, (), found)
    return Module(frozenset(found), _interface(root), count_statements(root, _STATEMENTS, _IMPORTS))


def _name(node: Node) -> str:
    return text(field(node, "name"))


def _walk(node: Node, scope: tuple[str, ...], found: set[str]) -> None:
    for child in kids(node):
        if child.type == "decorated_definition":
            # a decorator is logic of its own, so the function it wraps never counts as passing on
            definition = field(child, "definition")
            if definition is not None:
                _visit(definition, scope, found, decorated=True)
        else:
            _visit(child, scope, found, decorated=False)


def _visit(node: Node, scope: tuple[str, ...], found: set[str], *, decorated: bool) -> None:
    body = field(node, "body")
    if node.type == "class_definition" and body is not None:
        if "Protocol" not in text(field(node, "superclasses")):  # a Protocol only lists signatures
            _walk(body, (*scope, _name(node)), found)
    elif node.type == "function_definition" and body is not None:
        if not decorated and _forwards(node, body):
            found.add(".".join((*scope, _name(node))))
        _walk(body, (*scope, _name(node)), found)
    else:
        _walk(node, scope, found)


def _forwards(function: Node, body: Node) -> bool:
    name = _name(function)
    if name.startswith("__") and name.endswith("__"):
        return False
    statements = kids(body)
    if statements and _is_docstring(statements[0]):
        statements = statements[1:]
    call = sole(statements, _WRAPPERS)
    if call is None or call.type != "call":
        return False
    arguments = field(call, "arguments")
    if arguments is None or arguments.type != "argument_list":
        return False
    return forwards(_params(function), [_arg(a) for a in kids(arguments)])


def _is_docstring(node: Node) -> bool:
    inner = kids(node)
    return node.type == "expression_statement" and len(inner) == 1 and inner[0].type == "string"


def _params(function: Node) -> list[str | None]:
    parameters = field(function, "parameters")
    names = [_param(p) for p in kids(parameters)] if parameters is not None else []
    return names[1:] if names and names[0] in _SELF else names


def _param(node: Node) -> str | None:
    match node.type:
        case "identifier":
            return text(node)
        case "list_splat_pattern" | "dictionary_splat_pattern":
            prefix = "*" if node.type == "list_splat_pattern" else "**"
            return prefix + text(kids(node)[0]) if kids(node) else None
        case "typed_parameter":
            inner = kids(node)
            return _param(inner[0]) if inner else None
        case "default_parameter" | "typed_default_parameter":
            name = field(node, "name")
            return _param(name) if name is not None else None
    return None


def _arg(node: Node) -> str | None:
    match node.type:
        case "identifier":
            return text(node)
        case "list_splat" | "dictionary_splat":
            prefix = "*" if node.type == "list_splat" else "**"
            return prefix + text(kids(node)[0]) if kids(node) else None
        case "keyword_argument":
            name, value = text(field(node, "name")), text(field(node, "value"))
            return name if name == value else None
    return None


def _weight(function: Node) -> int:
    return 1 + len([p for p in _params(function) if p is not None])


def _interface(root: Node) -> int:
    exported = _exports(root)
    size = 0
    for child in kids(root):
        node = field(child, "definition") if child.type == "decorated_definition" else child
        if node is None or not _public(_name(node), exported):
            continue
        if node.type == "function_definition":
            size += _weight(node)
        elif node.type == "class_definition":
            size += 1 + _methods(node)
    return size


def _public(name: str, exported: set[str] | None) -> bool:
    return name in exported if exported is not None else bool(name) and not name.startswith("_")


def _methods(cls: Node) -> int:
    body = field(cls, "body")
    size = 0
    for child in kids(body) if body is not None else []:
        node = field(child, "definition") if child.type == "decorated_definition" else child
        if node is None or node.type != "function_definition":
            continue
        name = _name(node)
        if name == "__init__" or not name.startswith("_"):
            size += _weight(node)
    return size


def _exports(root: Node) -> set[str] | None:
    """The names ``__all__`` lists, or ``None`` when the module has no such list."""
    for child in kids(root):
        inner = kids(child) if child.type == "expression_statement" else []
        is_all = (
            len(inner) == 1
            and inner[0].type == "assignment"
            and text(field(inner[0], "left")) == "__all__"
        )
        if is_all:
            right = field(inner[0], "right")
            items = kids(right) if right is not None else []
            return {text(i).strip("'\"") for i in items if i.type == "string"}
    return None


def imports(root: Node) -> tuple[str, ...]:
    """The module every import names, wherever it stands; ``from m import n`` names ``m.n``.

    The resolver falls back to ``m`` when ``m.n`` is not a module of the project. A relative
    import keeps its dots: ``from ..a import q`` is ``..a.q``.
    """
    found: list[str] = []
    for node in walk(root):
        if node.type == "import_statement":
            found.extend(_dotted(n) for n in node.children_by_field_name("name"))
        elif node.type == "import_from_statement":
            base = text(field(node, "module_name"))
            names = [_dotted(n) for n in node.children_by_field_name("name")]
            found.extend(f"{base}{'' if base.endswith('.') else '.'}{n}" for n in names)
            if any(c.type == "wildcard_import" for c in node.children):
                found.append(base)
    return tuple(found)


def _dotted(node: Node) -> str:
    return text(field(node, "name")) if node.type == "aliased_import" else text(node)


_ABSTRACT_BASES = re.compile(r"\b(ABC|Protocol)\b")
_ABSTRACT_METHOD = re.compile(r"\babstractmethod\b")


def types(root: Node) -> tuple[int, int]:
    """The abstract types and all the types: a class built on ``ABC`` or ``Protocol``, or with an
    abstract method, is abstract."""
    classes = [n for n in walk(root) if n.type == "class_definition"]
    return sum(1 for c in classes if _abstract(c)), len(classes)


def _abstract(cls: Node) -> bool:
    if _ABSTRACT_BASES.search(text(field(cls, "superclasses"))):
        return True
    body = field(cls, "body")
    decorators = [
        d
        for m in (kids(body) if body is not None else [])
        if m.type == "decorated_definition"
        for d in kids(m)
    ]
    return any(_ABSTRACT_METHOD.search(text(d)) for d in decorators if d.type == "decorator")
