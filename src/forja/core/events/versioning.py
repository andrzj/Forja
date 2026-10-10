import json
from collections.abc import Mapping
from typing import Any

from pydantic import ValidationError

from forja.core.events.errors import UnsupportedSchemaVersion
from forja.core.events.models import EVENT_ADAPTER, SCHEMA_VERSION, Event, compute_hash

Upgrader = Any  # Callable[[dict[str, Any]], dict[str, Any]]: version N record -> version N+1

# Version N -> function producing version N+1. Empty while version 1 is the only one.
UPGRADERS: Mapping[int, Upgrader] = {}


class BadLine(Exception):
    """The line is not a valid event: not JSON, wrong hash or wrong shape."""


def parse_line(raw: bytes, upgraders: Mapping[int, Upgrader] = UPGRADERS) -> Event:
    """Decode one stored line, verify its hash, and convert it to the current schema.

    The hash is checked on the record as it was written, before any conversion. A version newer
    than this code understands raises ``UnsupportedSchemaVersion`` instead of being misread.
    """
    try:
        data = json.loads(raw)
    except ValueError as error:
        raise BadLine(f"not valid JSON: {error}") from None
    if not isinstance(data, dict):
        raise BadLine("not a JSON object")
    version = data.get("schema_version")
    if not isinstance(version, int) or isinstance(version, bool):
        raise BadLine("missing schema_version")
    if version > SCHEMA_VERSION:
        raise UnsupportedSchemaVersion(version, SCHEMA_VERSION)
    stored_hash = data.get("hash")
    body = {key: value for key, value in data.items() if key != "hash"}
    if stored_hash != compute_hash(body):
        raise BadLine("hash does not match the content")
    while version < SCHEMA_VERSION:
        if version not in upgraders:
            raise UnsupportedSchemaVersion(version, SCHEMA_VERSION)
        data = upgraders[version](data)
        version += 1
        data["schema_version"] = version
    try:
        return EVENT_ADAPTER.validate_python(data)
    except ValidationError as error:
        raise BadLine(f"invalid event: {error.errors()[0]['msg']}") from None
