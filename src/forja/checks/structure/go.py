"""Go: pass-through functions and the size of the exported surface."""

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
        "method_declaration",
        "short_var_declaration",
        "var_declaration",
        "const_declaration",
        "type_declaration",
    }
)
_WRAPPERS = frozenset({"return_statement", "expression_statement", "expression_list"})
_FUNCTIONS = frozenset({"function_declaration", "method_declaration"})


def read(root: Node) -> Module:
    found = {_qualified(node) for node in walk(root) if node.type in _FUNCTIONS and _forwards(node)}
    return Module(frozenset(found), _interface(root), count_statements(root, _STATEMENTS))


def _qualified(function: Node) -> str:
    name = text(field(function, "name"))
    receiver = field(function, "receiver")
    holders = kids(receiver) if receiver is not None else []
    kind = field(holders[0], "type") if holders else None
    return f"{text(kind).lstrip('*')}.{name}" if kind is not None else name


def _forwards(function: Node) -> bool:
    body = field(function, "body")
    if body is None:
        return False
    statements = kids(body)
    if len(statements) == 1 and statements[0].type == "statement_list":
        statements = kids(statements[0])
    call = sole(statements, _WRAPPERS)
    if call is not None and call.type == "expression_list":  # `return f(x)` wraps it once more
        inner = kids(call)
        call = inner[0] if len(inner) == 1 else None
    if call is None or call.type != "call_expression":
        return False
    arguments = field(call, "arguments")
    if arguments is None:
        return False
    return forwards(_params(function), [_arg(a) for a in kids(arguments)])


def _params(function: Node) -> list[str | None]:
    parameters = field(function, "parameters")
    names: list[str | None] = []
    for declaration in kids(parameters) if parameters is not None else []:
        declared = declaration.children_by_field_name("name")
        if not declared:
            names.append(None)  # a parameter without a name cannot be passed on
        elif declaration.type == "variadic_parameter_declaration":
            names.append("*" + text(declared[0]))
        else:
            names.extend(text(n) for n in declared)
    return names


def _arg(node: Node) -> str | None:
    if node.type == "identifier":
        return text(node)
    if node.type == "variadic_argument" and kids(node):
        return "*" + text(kids(node)[0])
    return None


def _exported(name: str) -> bool:
    return name[:1].isupper()


def _interface(root: Node) -> int:
    size = 0
    for child in kids(root):
        if child.type in _FUNCTIONS and _exported(text(field(child, "name"))):
            size += 1 + len([p for p in _params(child) if p is not None])
        elif child.type == "type_declaration":
            size += sum(1 for spec in kids(child) if _exported(text(field(spec, "name"))))
    return size
