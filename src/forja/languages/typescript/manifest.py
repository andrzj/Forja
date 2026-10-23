"""The packages ``package.json`` declares, from the registry: ``dependencies``,
``devDependencies``, ``optionalDependencies`` and ``peerDependencies``. A dependency on a path, a
workspace, a git repository or a URL is not in the registry and is left out; ``npm:`` aliases
name the package they point to."""

import json
import re
from typing import Any

from forja.core.adapters.manifests import file_name

SECTIONS = ("dependencies", "devDependencies", "optionalDependencies", "peerDependencies")
NOT_FROM_THE_REGISTRY = ("file:", "link:", "workspace:", "git:", "git+", "http:", "https:",
                         "github:", "gitlab:", "bitbucket:", "gist:")  # fmt: skip
_REPOSITORY = re.compile(r"[\w.-]+/[\w.-]+(#.*)?")  # npm reads ``user/repo`` as GitHub


def declared_dependencies(path: str, text: str) -> frozenset[str] | None:
    if file_name(path) != "package.json":
        return None
    try:
        data = json.loads(text)
    except ValueError as error:
        raise ValueError(f"not valid JSON: {error}") from None
    if not isinstance(data, dict):
        raise ValueError("not a JSON object")
    found = set()
    for section in SECTIONS:
        entries: Any = data.get(section, {})
        if not isinstance(entries, dict):
            continue
        for name, spec in entries.items():
            registry_name = _from_registry(str(name), spec)
            if registry_name:
                found.add(registry_name)
    return frozenset(found)


def _from_registry(name: str, spec: Any) -> str | None:
    if not isinstance(spec, str):
        return name
    if spec.startswith("npm:"):
        target = spec[4:]
        at = target.rfind("@")
        return target[:at] if at > 0 else target
    if spec.startswith(NOT_FROM_THE_REGISTRY) or _REPOSITORY.fullmatch(spec):
        return None
    return name
