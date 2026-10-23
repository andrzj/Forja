"""The artifacts a Java build declares, as ``group:artifact``: ``dependency`` elements of
``pom.xml``, and the ``"group:artifact:version"`` strings of a Gradle ``build.gradle[.kts]``.
Coordinates built from properties (``${...}``) and version catalogs (``libs.x``) are not resolved
and are left out."""

import re

from forja.core.adapters.manifests import file_name, local, parse_xml

_GRADLE_BUILD = re.compile(r"build\.gradle(\.kts)?")
_STRING_NOTATION = re.compile(
    r"""^\s*[A-Za-z]\w*\s*\(?\s*["']([A-Za-z0-9_.-]+):([A-Za-z0-9_.-]+)(?::[^"']*)?["']"""
)


def declared_dependencies(path: str, text: str) -> frozenset[str] | None:
    name = file_name(path)
    if name == "pom.xml":
        return _pom(text)
    if _GRADLE_BUILD.fullmatch(name):
        return _gradle(text)
    return None


def _pom(text: str) -> frozenset[str]:
    found = set()
    for element in parse_xml(text).iter():
        if local(element.tag) != "dependency":
            continue
        parts = {local(child.tag): (child.text or "").strip() for child in element}
        group, artifact = parts.get("groupId", ""), parts.get("artifactId", "")
        if group and artifact and "${" not in group + artifact:
            found.add(f"{group}:{artifact}")
    return frozenset(found)


def _gradle(text: str) -> frozenset[str]:
    return frozenset(
        f"{found[1]}:{found[2]}"
        for line in text.splitlines()
        if (found := _STRING_NOTATION.match(line))
    )
