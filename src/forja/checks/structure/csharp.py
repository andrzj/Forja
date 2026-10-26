"""C#: pass-through methods and the size of the public surface."""

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
        "method_declaration",
        "constructor_declaration",
        "property_declaration",
        "field_declaration",
        "class_declaration",
        "interface_declaration",
        "struct_declaration",
        "record_declaration",
        "enum_declaration",
    }
)
_SKIP = frozenset({"global_statement"})  # wraps a statement that is counted on its own
_TYPES = frozenset(
    {
        "class_declaration",
        "interface_declaration",
        "struct_declaration",
        "record_declaration",
        "enum_declaration",
    }
)
_WRAPPERS = frozenset({"return_statement", "expression_statement"})


def read(root: Node) -> Module:
    found = {name for node in walk(root) if node.type in _TYPES for name in _forwarders(node)}
    return Module(frozenset(found), _interface(root), count_statements(root, _STATEMENTS, _SKIP))


def _forwarders(cls: Node) -> list[str]:
    body = field(cls, "body")
    methods = [m for m in kids(body) if m.type == "method_declaration"] if body else []
    return [f"{text(field(cls, 'name'))}.{text(field(m, 'name'))}" for m in methods if _forwards(m)]


def _forwards(method: Node) -> bool:
    body = field(method, "body")  # an abstract method has none
    if body is None:
        return False
    if body.type == "arrow_expression_clause":
        inner = kids(body)
        call = inner[0] if len(inner) == 1 else None
    else:
        call = sole(kids(body), _WRAPPERS)
    if call is None or call.type != "invocation_expression":
        return False
    arguments = field(call, "arguments")
    if arguments is None:
        return False
    return forwards(_params(method), [_arg(a) for a in kids(arguments)])


def _params(method: Node) -> list[str | None]:
    parameters = field(method, "parameters")
    return [
        text(field(p, "name")) if p.type == "parameter" else None
        for p in (kids(parameters) if parameters is not None else [])
    ]


def _arg(node: Node) -> str | None:
    """A bare name; ``ref``, ``out`` and named arguments add tokens, so they do not count."""
    inner = kids(node)
    if node.type == "argument" and len(node.children) == 1 and inner[0].type == "identifier":
        return text(inner[0])
    return None


def _public(node: Node, implicit: bool) -> bool:
    return implicit or any(c.type == "modifier" and text(c) == "public" for c in node.children)


def _types(node: Node) -> list[Node]:
    """The types declared at the top, looking through namespaces."""
    found = []
    for child in kids(node):
        if child.type in _TYPES:
            found.append(child)
        elif child.type == "namespace_declaration":
            body = field(child, "body")
            found.extend(_types(body) if body is not None else [])
    return found


def _interface(root: Node) -> int:
    size = 0
    for declared in _types(root):
        if not _public(declared, implicit=False):
            continue
        size += 1
        body = field(declared, "body")
        interface = declared.type == "interface_declaration"
        for member in kids(body) if body is not None else []:
            if member.type in ("method_declaration", "constructor_declaration") and _public(
                member, implicit=interface
            ):
                size += 1 + len([p for p in _params(member) if p is not None])
    return size


def imports(root: Node) -> tuple[str, ...]:
    """What every ``using`` names: a namespace, a static type or an alias target."""
    directives = (kids(n) for n in walk(root) if n.type == "using_directive")
    return tuple(text(named[-1]) for named in directives if named)
