"""Java: pass-through methods and the size of the public surface."""

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
        "local_variable_declaration",
        "field_declaration",
        "method_declaration",
        "constructor_declaration",
        "class_declaration",
        "interface_declaration",
        "enum_declaration",
        "record_declaration",
    }
)
_TYPES = frozenset(
    {"class_declaration", "interface_declaration", "enum_declaration", "record_declaration"}
)
_WRAPPERS = frozenset({"return_statement", "expression_statement"})


def read(root: Node) -> Module:
    found = {name for node in walk(root) if node.type in _TYPES for name in _forwarders(node)}
    return Module(frozenset(found), _interface(root), count_statements(root, _STATEMENTS))


def _forwarders(cls: Node) -> list[str]:
    body = field(cls, "body")
    methods = [m for m in kids(body) if m.type == "method_declaration"] if body else []
    return [f"{text(field(cls, 'name'))}.{text(field(m, 'name'))}" for m in methods if _forwards(m)]


def _forwards(method: Node) -> bool:
    body = field(method, "body")  # an abstract method has none
    if body is None:
        return False
    call = sole(kids(body), _WRAPPERS)
    if call is None or call.type != "method_invocation":
        return False
    arguments = field(call, "arguments")
    if arguments is None:
        return False
    args = [text(a) if a.type == "identifier" else None for a in kids(arguments)]
    return forwards(_params(method), args)


def _params(method: Node) -> list[str | None]:
    parameters = field(method, "parameters")
    names: list[str | None] = []
    for parameter in kids(parameters) if parameters is not None else []:
        if parameter.type == "formal_parameter":
            names.append(text(field(parameter, "name")))
        elif parameter.type == "spread_parameter":  # varargs arrive as an array, passed on as one
            declarator = next((k for k in kids(parameter) if k.type == "variable_declarator"), None)
            names.append(text(field(declarator, "name")) if declarator is not None else None)
        else:
            names.append(None)
    return names


def _public(node: Node, implicit: bool) -> bool:
    modifiers = next((k for k in kids(node) if k.type == "modifiers"), None)
    return implicit or (
        modifiers is not None and any(c.type == "public" for c in modifiers.children)
    )


def _interface(root: Node) -> int:
    size = 0
    for child in kids(root):
        if child.type not in _TYPES or not _public(child, implicit=False):
            continue
        size += 1
        body = field(child, "body")
        interface = child.type == "interface_declaration"
        for member in kids(body) if body is not None else []:
            if member.type in ("method_declaration", "constructor_declaration") and _public(
                member, implicit=interface
            ):
                size += 1 + len([p for p in _params(member) if p is not None])
    return size


def imports(root: Node) -> tuple[str, ...]:
    """The name every import declares: ``a.b.*`` for a wildcard, the member of a static import."""
    found: list[str] = []
    for node in walk(root):
        if node.type != "import_declaration":
            continue
        names = [text(c) for c in kids(node) if c.type != "asterisk"]
        star = any(c.type == "asterisk" for c in kids(node))
        if names:
            found.append(f"{names[0]}.*" if star else names[0])
    return tuple(found)


_DECLARATIONS = frozenset(
    {
        "class_declaration",
        "interface_declaration",
        "enum_declaration",
        "record_declaration",
        "annotation_type_declaration",
    }
)
_INTERFACES = frozenset({"interface_declaration", "annotation_type_declaration"})


def types(root: Node) -> tuple[int, int]:
    """The interfaces and abstract classes, and all the types."""
    found = [n for n in walk(root) if n.type in _DECLARATIONS]
    abstract = sum(1 for n in found if n.type in _INTERFACES or _abstract(n))
    return abstract, len(found)


def _abstract(node: Node) -> bool:
    return any("abstract" in text(c).split() for c in kids(node) if c.type == "modifiers")


def declared(root: Node) -> tuple[str, ...]:
    """The package, then the qualified name of each top-level type."""
    package = next((text(kids(n)[0]) for n in kids(root) if n.type == "package_declaration"), "")
    names = (text(field(n, "name")) for n in kids(root) if n.type in _DECLARATIONS)
    return (package, *(f"{package}.{n}" if package else n for n in names))
