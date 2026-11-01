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
        if "://" in requirement:
            continue  # a package that is not in the registry
        if name := _name(requirement):  # an option, a comment, a blank or a path has none
            found.add(name)
    return frozenset(found)


def _plain_requirement(requirement: str) -> bool:
    """A requirement that names a package of the registry: no option, no URL, no direct reference
    (``name @ url``), no path."""
    text = requirement.strip()
    if not text or text.startswith(("-", ".", "/")) or "://" in text or "@" in text:
        return False
    return _name(text) is not None


def only_dependencies_changed(path: str, before: str, after: str) -> bool | None:
    """Whether the edit of a Python manifest touches nothing but the dependencies it declares, and
    each one it adds is a plain registry requirement. ``None`` when ``path`` is not a Python
    manifest. Anything else in ``pyproject.toml`` (the build system, the tools, the entry points)
    is configuration the agent may not change, and an option or a URL in a requirements file
    can point the installer at another index or another source."""
    name = file_name(path)
    try:
        if name == "pyproject.toml":
            return _pyproject_edit(before, after)
        if _REQUIREMENTS.fullmatch(name):
            return _requirements_edit(before, after)
    except (ValueError, tomllib.TOMLDecodeError):
        return False
    return None


def _without_dependencies(data: dict[str, object]) -> dict[str, object]:
    rest = {key: value for key, value in data.items() if key != "dependency-groups"}
    project = rest.get("project")
    if isinstance(project, dict):
        rest["project"] = {
            key: value
            for key, value in project.items()
            if key not in ("dependencies", "optional-dependencies")
        }
    return rest


def _pyproject_edit(before: str, after: str) -> bool:
    old = tomllib.loads(before) if before.strip() else {}
    new = tomllib.loads(after)
    if _without_dependencies(old) != _without_dependencies(new):
        return False
    return all(
        _plain_requirement(item)
        for item in _requirement_strings(new)
        if item not in _requirement_strings(old)
    )


def _requirement_strings(data: dict[str, object]) -> list[str]:
    project = data.get("project", {})
    lists: list[object] = [project.get("dependencies", []) if isinstance(project, dict) else []]
    if isinstance(project, dict):
        lists += list(project.get("optional-dependencies", {}).values())
    groups = data.get("dependency-groups", {})
    if isinstance(groups, dict):
        lists += list(groups.values())
    return [
        item
        for items in lists
        if isinstance(items, list)
        for item in items
        if isinstance(item, str)
    ]


def _requirements_edit(before: str, after: str) -> bool:
    kept = {line.strip() for line in before.splitlines()}
    for line in after.splitlines():
        text = line.split(" #", 1)[0].strip()
        if line.strip() in kept or not text or text.startswith("#"):
            continue
        if not _plain_requirement(text):
            return False
    return True
