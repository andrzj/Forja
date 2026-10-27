"""Gate 11: whether the output of the new version equals the one of the base, by the case's rule.

Three rules, no others: ``bytes`` (exactly), ``json`` (the same document, whatever the key order
and the spacing) and ``ignore`` (the bytes left after the lines a pattern finds are dropped). What
no rule excuses is a difference. The text of a difference says where and how big, never what the
output held: the output of a program may carry data that must not travel into a message.
"""

import json
import re
from collections.abc import Callable

from forja.core.policy.differential import BYTES, FILE, IGNORE, JSON, DifferentialOutput


def describe(output: DifferentialOutput) -> str:
    """How the report names an output: ``stdout``, ``exit_code`` or ``file <path>``."""
    return f"{output.kind} {output.path}" if output.kind == FILE else output.kind


def compare_output(
    output: DifferentialOutput, before: bytes | None, after: bytes | None
) -> str | None:
    """``None`` when the outputs are the same by the rule, otherwise a short account of the
    first difference. ``None`` as an output is a file that was not there."""
    if before is None or after is None:
        if before is None and after is None:
            return None
        return "the file is missing in " + ("the base" if before is None else "the new version")
    if output.rule == BYTES:
        return _first_difference(before, after, "")
    if output.rule == JSON:
        return _json_difference(before, after)
    assert output.rule == IGNORE
    kept = _without_ignored(output.ignore)
    return _first_difference(kept(before), kept(after), " after dropping the ignored lines")


def _first_difference(before: bytes, after: bytes, note: str) -> str | None:
    if before == after:
        return None
    offset = next(
        (i for i, (a, b) in enumerate(zip(before, after, strict=False)) if a != b),
        min(len(before), len(after)),
    )
    line = before.count(b"\n", 0, offset) + 1
    return (
        f"differs at byte {offset} (line {line}){note}; "
        f"the base has {len(before)} bytes, the new version {len(after)}"
    )


def _json_difference(before: bytes, after: bytes) -> str | None:
    canonical = []
    for side, raw in (("the base", before), ("the new version", after)):
        try:
            document = json.loads(raw.decode("utf-8"))
        except ValueError:  # includes a UnicodeDecodeError
            return f"{side} is not valid JSON"
        canonical.append(json.dumps(document, sort_keys=True, separators=(",", ":")).encode())
    return _first_difference(canonical[0], canonical[1], " in the canonical JSON")


def _without_ignored(patterns: tuple[str, ...]) -> Callable[[bytes], bytes]:
    found = [re.compile(pattern) for pattern in patterns]

    def kept(raw: bytes) -> bytes:
        return b"".join(
            line
            for line in raw.splitlines(keepends=True)
            if not any(p.search(line.decode("utf-8", errors="replace")) for p in found)
        )

    return kept
