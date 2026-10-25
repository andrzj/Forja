"""The input of the specifier cut into elements with a stable id, before any model sees it.

The cut is text, not understanding: a list item is an element, and so is a paragraph that is not a
list. A heading alone is not one. Prose in one paragraph is one big element, so the traceability
that rests on these ids is as coarse as the text is.
"""

import re
from dataclasses import dataclass

_ITEM = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(?P<text>.*)$")
_HEADING = re.compile(r"^\s*#{1,6}(?:\s|$)")


@dataclass(frozen=True)
class Element:
    id: str
    text: str


def _joined(lines: list[str]) -> str:
    return " ".join(" ".join(lines).split())


def _pieces(block: list[str]) -> list[str]:
    """The elements of one paragraph: its items, and the lines before the first item."""
    pieces: list[list[str]] = []
    for line in block:
        item = _ITEM.match(line)
        if item:
            pieces.append([item["text"]])
        elif pieces:
            pieces[-1].append(line)
        else:
            pieces.append([line])
    return [text for text in (_joined(piece) for piece in pieces) if text]


def elements_of(text: str) -> tuple[Element, ...]:
    """The elements of ``text`` in order, numbered ``E1``, ``E2``..."""
    blocks: list[list[str]] = [[]]
    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if line.strip():
            blocks[-1].append(line)
        elif blocks[-1]:
            blocks.append([])
    found: list[str] = []
    for block in blocks:
        if block and not all(_HEADING.match(line) for line in block):
            found += _pieces(block)
    return tuple(Element(f"E{number}", item) for number, item in enumerate(found, start=1))
