"""The modules ``go.mod`` requires (go.dev/ref/mod): ``require path version`` on one line, or a
``require ( ... )`` block with one such line per module. ``replace`` and ``exclude`` do not add
a requirement."""

from forja.core.adapters.manifests import file_name


def declared_dependencies(path: str, text: str) -> frozenset[str] | None:
    if file_name(path) != "go.mod":
        return None
    found = set()
    inside = False
    for raw in text.splitlines():
        line = raw.split("//", 1)[0].strip()
        if not line:
            continue
        if inside:
            if line == ")":
                inside = False
            else:
                found.add(line.split()[0])
        elif line == "require (":
            inside = True
        elif line.startswith("require "):
            fields = line.removeprefix("require ").split()
            if fields:
                found.add(fields[0])
    return frozenset(found)
