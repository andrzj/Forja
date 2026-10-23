"""The NuGet packages a .NET project declares: ``PackageReference`` and ``PackageVersion``
elements (``Include`` is the package id) of ``*.csproj`` and ``Directory.Packages.props``, and the
``package`` elements of a ``packages.config``."""

from forja.core.adapters.manifests import file_name, local, parse_xml

PROJECT_FILES = (".csproj", ".props")


def declared_dependencies(path: str, text: str) -> frozenset[str] | None:
    name = file_name(path)
    if not (name.endswith(PROJECT_FILES) or name == "packages.config"):
        return None
    found = set()
    for element in parse_xml(text).iter():
        tag = local(element.tag)
        if tag in ("PackageReference", "PackageVersion"):
            identifier = element.get("Include")
        elif tag == "package" and name == "packages.config":
            identifier = element.get("id")
        else:
            continue
        if identifier and "$(" not in identifier:
            found.add(identifier)
    return frozenset(found)
