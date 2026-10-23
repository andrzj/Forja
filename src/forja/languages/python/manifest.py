"""The packages a Python manifest declares: ``pyproject.toml`` (PEP 621 ``project.dependencies``,
``project.optional-dependencies`` and PEP 735 ``dependency-groups``) and ``requirements*.txt``.
The name is the start of the PEP 508 requirement string."""

import re
import tomllib

from forja.core.adapters.manifests import file_name

_NAME = re.compile(r"\s*([A-Za-z0-9][A-Za-z0-9._-]*)")
_REQUIREMENTS = re.compile(r"requirements[\w.-]*\.txt", re.IGNORECASE)


def _name(requirement: str) -> str | None:
    found = _NAME.match(requirement)
    return found[1] if found else None


def declared_dependencies(path: str, text: str) -> frozenset[str] | None:
    """The names declared, ``None`` when ``path`` is not a Python manifest, ``ValueError`` when
    it is one that cannot be read."""
    name = file_name(path)
    if name == "pyproject.toml":
        return _pyproject(text)
    if _REQUIREMENTS.fullmatch(name):
        return _requirements(text)
    return None


def _pyproject(text: str) -> frozenset[str]:
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        raise ValueError(f"not valid TOML: {error}") from None
    project = data.get("project", {})
    lists = [project.get("dependencies", [])]
    lists += list(project.get("optional-dependencies", {}).values())
    lists += list(data.get("dependency-groups", {}).values())
    found = {
        _name(item)
        for items in lists
        for item in items
        if isinstance(item, str)  # a group may include another: that is a table
    }
    return frozenset(name for name in found if name)


def _requirements(text: str) -> frozenset[str]:
    found = set()
    for line in text.splitlines():
        requirement = line.split(" #", 1)[0].strip()
        if not requirement or requirement.startswith(("-", "#")) or "://" in requirement:
            continue  # an option, a comment or a package that is not in the registry
        if requirement.startswith((".", "/")):
            continue
        if name := _name(requirement):
            found.add(name)
    return frozenset(found)
