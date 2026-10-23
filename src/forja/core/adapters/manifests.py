"""Reading a dependency manifest the attempt wrote: its text is not to be trusted."""

import xml.etree.ElementTree as ET  # noqa: S405 - DOCTYPE and entities are refused below
from pathlib import PurePosixPath


def file_name(path: str) -> str:
    return PurePosixPath(path.replace("\\", "/")).name


def parse_xml(text: str) -> ET.Element:
    """The root of an XML manifest. A document type declaration is how entities get defined (and
    expanded without bound), and no manifest needs one, so it is refused."""
    if "<!DOCTYPE" in text.upper() or "<!ENTITY" in text.upper():
        raise ValueError("a manifest with a DOCTYPE or entity declaration is not read")
    try:
        return ET.fromstring(text)  # noqa: S314 - see above
    except ET.ParseError as error:
        raise ValueError(f"not valid XML: {error}") from None


def local(tag: str) -> str:
    """An element name without its namespace."""
    return tag.rsplit("}", 1)[-1]
