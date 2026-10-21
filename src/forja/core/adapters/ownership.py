"""Whether a test id can belong to a test file, for runners whose ids do not carry the path.

The id names the test; the file has to say that name. The names are compared as they are
written in the source, so a subtest or a parameterised case still belongs to its test.
"""

import re


def says(text: str, name: str) -> bool:
    """``name`` is written in ``text`` as a whole word."""
    return bool(name) and re.search(rf"(?<![\w$]){re.escape(name)}(?![\w$])", text) is not None


def dotted_names(test_id: str) -> tuple[str, str] | None:
    """The class and the method of ``Namespace.Class.method(args)`` or ``Class.method[1]``."""
    base = re.split(r"[(\[<]", test_id, maxsplit=1)[0].strip()
    parts = [p for p in re.split(r"[.$+]", base) if p]
    return (parts[-2], parts[-1]) if len(parts) >= 2 else None
