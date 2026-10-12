"""Turning the text of a value into a Python value."""

UNITS = {"kb": 1024, "mb": 1024**2, "gb": 1024**3}


def convert(text):
    """The value a piece of text stands for; text that stands for nothing stays text."""
    if not isinstance(text, str):
        return text
    value = text.strip()
    lowered = value.lower()
    if lowered in ("true", "yes", "on"):
        return True
    if lowered in ("false", "no", "off"):
        return False
    if lowered in ("none", "null", ""):
        return None
    if value.startswith("0x") or value.startswith("0X"):
        try:
            return int(value, 16)
        except ValueError:
            return value
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [convert(part) for part in inner.split(",")]
    sign = 1
    body = value
    if len(body) > 1 and body[0] in "+-":
        sign = -1 if body[0] == "-" else 1
        body = body[1:]
    if body.isdigit():
        return sign * int(body)
    if body.count(".") == 1 and body.replace(".", "").isdigit():
        return sign * float(body)
    if len(body) > 2 and body[-2:].lower() in UNITS and body[:-2].isdigit():
        return sign * int(body[:-2]) * UNITS[body[-2:].lower()]
    return value
