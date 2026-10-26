"""Go: a directory is a package, and an import path under the module path names a directory."""

import posixpath
import re
from collections.abc import Mapping

from forja.checks.architecture.facts import FileFacts

_MODULE = re.compile(r"^\s*module\s+(\S+)", re.MULTILINE)


def module_path(go_mod: str) -> str | None:
    """The module path ``go.mod`` declares, or ``None`` when it declares none."""
    found = _MODULE.search(go_mod)
    return found.group(1).strip('"`') if found else None


def resolve(facts: Mapping[str, FileFacts], module: str) -> set[tuple[str, str]]:
    folders = {_dir(path) for path in facts}
    edges: set[tuple[str, str]] = set()
    for path, found in facts.items():
        for target in found.imports:
            if target == module:
                inside = "."
            elif target.startswith(f"{module}/"):
                inside = target[len(module) + 1 :]
            else:
                continue
            if inside in folders:
                edges.add((_dir(path), inside))
    return edges


def _dir(path: str) -> str:
    return posixpath.dirname(path) or "."
