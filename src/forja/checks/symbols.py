"""The named declarations of a source file, as a change record lists them.

One reader for the six languages, over the syntax trees ``checks.structure`` already parses. Only
declarations count (no parameters, accessors or enum members), and a ``const f = () => ...`` is
one only when its value is a function.
"""

from dataclasses import dataclass

from tree_sitter import Node

from forja.checks.structure import SyntaxProblem, tree_of
from forja.checks.structure.nodes import text

KINDS = {
    "python": {"function_definition": "function", "class_definition": "class"},
    "go": {
        "function_declaration": "function",
        "method_declaration": "method",
        "type_spec": "type",
    },
    "java": {
        "class_declaration": "class",
        "method_declaration": "method",
        "interface_declaration": "interface",
        "record_declaration": "record",
        "enum_declaration": "enum",
    },
    "csharp": {
        "class_declaration": "class",
        "method_declaration": "method",
        "interface_declaration": "interface",
        "record_declaration": "record",
        "enum_declaration": "enum",
        "struct_declaration": "struct",
        "property_declaration": "property",
    },
    "javascript": {
        "function_declaration": "function",
        "class_declaration": "class",
        "method_definition": "method",
    },
    "typescript": {
        "function_declaration": "function",
        "class_declaration": "class",
        "method_definition": "method",
        "interface_declaration": "interface",
        "type_alias_declaration": "type",
        "enum_declaration": "enum",
    },
}
SCRIPTS = ("javascript", "typescript")
FUNCTION_VALUES = frozenset({"arrow_function", "function_expression", "function"})
CONTAINERS = frozenset({"class", "interface", "enum", "record", "struct"})
PRIVATE_MODIFIERS = frozenset({"private", "protected"})
MEMBER_OWNERS = ("class_declaration", "record_declaration", "struct_declaration")


@dataclass(frozen=True)
class Symbol:
    name: str  # qualified by the declarations around it: ``Class.method``
    kind: str
    public: bool
    shape: str  # what is compared to tell a symbol changed: only the header for a container


def symbols_in(path: str, source: str) -> tuple[Symbol, ...] | None:
    """The declarations in ``source``; ``None`` when the language is not read or the text does
    not parse, so a caller never takes an unreadable file for an empty one."""
    try:
        tree = tree_of(path, source)
    except SyntaxProblem:
        return None
    if tree is None:
        return None
    dialect, root = tree
    found: list[Symbol] = []
    _collect(root, dialect.language, source.encode("utf-8"), (), found)
    return tuple(found)


def _collect(
    node: Node, language: str, source: bytes, around: tuple[str, ...], found: list[Symbol]
) -> None:
    declared = _declaration(node, language)
    inside = around
    if declared is not None:
        name, kind = declared
        qualified = ".".join((*around, name))
        public = _public(node, language, name, around)
        found.append(Symbol(qualified, kind, public, _shape(node, kind, source)))
        inside = (*around, name)
    for child in node.children:
        _collect(child, language, source, inside, found)


def _declaration(node: Node, language: str) -> tuple[str, str] | None:
    name_node = node.child_by_field_name("name")
    if node.type == "variable_declarator" and language in SCRIPTS:
        value = node.child_by_field_name("value")
        if value is not None and value.type in FUNCTION_VALUES and name_node is not None:
            return text(name_node), "function"
        return None
    kind = KINDS[language].get(node.type)
    if kind is None or name_node is None:
        return None
    name = text(name_node)
    if language == "go" and node.type == "method_declaration":
        name = f"{_receiver(node)}.{name}"
    if language == "python" and kind == "function" and _in_class(node):
        kind = "method"
    return name, kind


def _in_class(node: Node) -> bool:
    parent = node.parent
    while parent is not None and parent.type not in ("function_definition", "class_definition"):
        parent = parent.parent
    return parent is not None and parent.type == "class_definition"


def _receiver(node: Node) -> str:
    receiver = node.child_by_field_name("receiver")
    if receiver is None:
        return "?"
    types = [n for n in _descendants(receiver) if n.type == "type_identifier"]
    return text(types[0]) if types else "?"


def _descendants(node: Node) -> list[Node]:
    pending, found = [node], []
    while pending:
        current = pending.pop()
        found.append(current)
        pending.extend(reversed(current.children))
    return found


def _shape(node: Node, kind: str, source: bytes) -> str:
    body = node.child_by_field_name("body")
    end = body.start_byte if kind in CONTAINERS and body is not None else node.end_byte
    return " ".join(source[node.start_byte : end].decode("utf-8", "replace").split())


def _public(node: Node, language: str, name: str, around: tuple[str, ...]) -> bool:
    last = name.rsplit(".", 1)[-1]
    if language == "python":
        return not any(part.startswith("_") for part in (*around, last))
    if language == "go":
        return last[:1].isupper()
    if language in ("java", "csharp"):
        return _declared_public(node)
    return _exported(node)


def _declared_public(node: Node) -> bool:
    parent = node.parent
    while parent is not None:
        if parent.type == "interface_declaration":  # its members are public without saying so
            return True
        if parent.type in MEMBER_OWNERS:
            break
        parent = parent.parent
    words = [text(child) for child in node.children if child.type in ("modifiers", "modifier")]
    return any("public" in word.split() for word in words)


def _exported(node: Node) -> bool:
    for child in node.children:
        if child.type == "accessibility_modifier" and text(child) in PRIVATE_MODIFIERS:
            return False
    parent = node.parent
    while parent is not None:
        if parent.type == "export_statement":
            return True
        parent = parent.parent
    return False
