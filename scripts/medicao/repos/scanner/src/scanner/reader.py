"""Reading a configuration file one line at a time."""


def parse_line(line, state):
    """Feed one line to the reader.

    ``state`` remembers the section, a value that continues on the next line and what was read so
    far under ``data``; it is changed as the lines come.
    """
    text = line.rstrip("\r\n")
    pending = state.get("pending")
    if pending is not None:
        if text.endswith("\\"):
            pending["value"] += text[:-1].strip()
            return ("continued", pending["key"])
        pending["value"] += text.strip()
        done = state["data"].setdefault(state.get("section", ""), {})
        done[pending["key"]] = pending["value"]
        state["pending"] = None
        return ("set", pending["key"])
    stripped = text.strip()
    if not stripped:
        return ("blank", None)
    if stripped[0] in "#;":
        return ("comment", None)
    if stripped[0] == "[":
        if not stripped.endswith("]"):
            raise ValueError(f"unclosed section: {stripped}")
        name = stripped[1:-1].strip()
        if not name:
            raise ValueError("empty section name")
        if name in state["data"] and state.get("strict"):
            raise ValueError(f"duplicate section: {name}")
        state["section"] = name
        state["data"].setdefault(name, {})
        return ("section", name)
    if "=" not in stripped:
        raise ValueError(f"no = in line: {stripped}")
    key, _, value = stripped.partition("=")
    key = key.strip()
    value = value.strip()
    if not key:
        raise ValueError("empty key")
    if " " in key:
        raise ValueError(f"space in key: {key}")
    if value.endswith("\\"):
        state["pending"] = {"key": key, "value": value[:-1].strip()}
        return ("started", key)
    if len(value) >= 2 and value[0] in "\"'" and value[-1] == value[0]:
        value = value[1:-1]
    section = state["data"].setdefault(state.get("section", ""), {})
    if key in section and state.get("strict"):
        raise ValueError(f"duplicate key: {key}")
    section[key] = value
    return ("set", key)
