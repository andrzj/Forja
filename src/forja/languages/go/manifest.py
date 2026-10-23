"""The modules ``go.mod`` requires (go.dev/ref/mod): ``require path version`` on one line, or a
``require ( ... )`` block with one such line per module. ``replace`` and ``exclude`` do not add
a requirement. The file is read as tokens, as Go reads it: parentheses stand apart whatever the
spacing (``require(``), and a module path may be quoted."""

from forja.core.adapters.manifests import file_name


def _module(token: str) -> str:
    return token.strip('"`')


def declared_dependencies(path: str, text: str) -> frozenset[str] | None:
    if file_name(path) != "go.mod":
        return None
    found = set()
    inside = False
    for raw in text.splitlines():
        tokens = raw.split("//", 1)[0].replace("(", " ( ").replace(")", " ) ").split()
        if not tokens:
            continue
        if inside:
            if tokens[0] != ")":
                found.add(_module(tokens[0]))
            inside = ")" not in tokens
        elif tokens[0] == "require":
            rest = tokens[1:]
            if rest[:1] == ["("]:
                rest = rest[1:]
                inside = ")" not in rest
            if rest and rest[0] != ")":
                found.add(_module(rest[0]))
    return frozenset(found)
