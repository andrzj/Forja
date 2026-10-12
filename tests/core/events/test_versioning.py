"""A line of the log is read only if it says which version it is, and a newer one is refused."""

import json
from pathlib import Path

import pytest

from forja.core.events.errors import UnsupportedSchemaVersion
from forja.core.events.models import SCHEMA_VERSION, compute_hash
from forja.core.events.versioning import BadLine, parse_line
from tests.core.events.support import create_run, open_log


@pytest.mark.parametrize("version", ["true", '"1"', "null", "1.5"])
def test_a_version_that_is_not_a_whole_number_is_a_missing_version(version: str) -> None:
    with pytest.raises(BadLine, match="missing schema_version"):
        parse_line(('{"schema_version": ' + version + "}").encode())


def line_of_version(tmp_path: Path, version: int) -> bytes:
    with open_log(tmp_path / "events.jsonl") as log:
        create_run(log)
    record = json.loads((tmp_path / "events.jsonl").read_bytes().splitlines()[0])
    record["schema_version"] = version
    body = {key: value for key, value in record.items() if key != "hash"}
    return json.dumps({**body, "hash": compute_hash(body)}).encode()


def test_an_older_line_is_converted_step_by_step_to_the_current_version(tmp_path: Path) -> None:
    line = line_of_version(tmp_path, 0)

    event = parse_line(line, {0: lambda record: dict(record)})

    assert event.schema_version == SCHEMA_VERSION


def test_an_older_line_with_no_way_to_convert_it_is_refused(tmp_path: Path) -> None:
    with pytest.raises(UnsupportedSchemaVersion):
        parse_line(line_of_version(tmp_path, 0), {})


def test_a_line_that_is_not_an_object_is_refused() -> None:
    with pytest.raises(BadLine, match="not a JSON object"):
        parse_line(b"[1, 2]")


def test_a_line_with_a_good_hash_but_the_wrong_shape_is_refused() -> None:
    body = {"schema_version": SCHEMA_VERSION, "nothing": "of an event"}
    line = json.dumps({**body, "hash": compute_hash(body)}).encode()

    with pytest.raises(BadLine, match="invalid event"):
        parse_line(line)
