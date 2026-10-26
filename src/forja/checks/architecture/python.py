"""Python: an import names a dotted module, found by the longest prefix that is a file."""

import posixpath
from collections.abc import Mapping

from forja.checks.architecture.facts import FileFacts

_INIT = ("__init__.py", "__init__.pyi")


def resolve(facts: Mapping[str, FileFacts]) -> set[tuple[str, str]]:
    """The edges between the directories that hold the files, as (importer, imported)."""
    packages = _packages(facts)
    names: dict[str, str] = {}
    for path in sorted(facts):
        module = packages[path][0]
        if module:
            names.setdefault(".".join(module), path)
    edges: set[tuple[str, str]] = set()
    for path, found in facts.items():
        package = packages[path][1]
        for target in found.imports:
            hit = _longest(_absolute(target, package), names)
            if hit is not None:
                edges.add((_dir(path), _dir(hit)))
    return edges


def _dir(path: str) -> str:
    return posixpath.dirname(path) or "."


def _packages(facts: Mapping[str, FileFacts]) -> dict[str, tuple[list[str], list[str]]]:
    """For each file, its module name and the package it sits in, both as lists of parts.

    A package is a chain of directories with an ``__init__`` file; a file outside any package is
    a module of its own at the top.
    """
    inits = {posixpath.dirname(p) for p in facts if posixpath.basename(p) in _INIT}
    result: dict[str, tuple[list[str], list[str]]] = {}
    for path in facts:
        package: list[str] = []
        folder = posixpath.dirname(path)
        while folder and folder in inits:
            package.insert(0, posixpath.basename(folder))
            folder = posixpath.dirname(folder)
        stem = posixpath.splitext(posixpath.basename(path))[0]
        result[path] = (package if stem == "__init__" else [*package, stem], package)
    return result


def _absolute(target: str, package: list[str]) -> list[str]:
    """The parts of the module ``target`` names from a file that sits in ``package``."""
    dots = len(target) - len(target.lstrip("."))
    rest = [part for part in target[dots:].split(".") if part]
    if not dots:
        return rest
    keep = len(package) - (dots - 1)
    return [*package[:keep], *rest] if keep >= 0 else []


def _longest(parts: list[str], names: Mapping[str, str]) -> str | None:
    for size in range(len(parts), 0, -1):
        hit = names.get(".".join(parts[:size]))
        if hit is not None:
            return hit
    return None
