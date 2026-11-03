"""The jscpd JSON report reader: clones, the new ones, and a report that is not one."""

import json
from pathlib import Path

import pytest

from forja.checks.duplication_report import Clone, CloneSide, read_clones


def side(name: str, start: int = 1, end: int = 9, *, located: bool = True) -> dict[str, object]:
    raw: dict[str, object] = {"name": name, "start": start, "end": end}
    if located:
        raw["startLoc"] = {"line": start, "column": 1, "position": 0}
        raw["endLoc"] = {"line": end, "column": 2, "position": 99}
    return raw


def entry(**changes: object) -> dict[str, object]:
    base: dict[str, object] = {
        "format": "python",
        "kind": "exact",
        "isNew": False,
        "lines": 9,
        "tokens": 60,
        "firstFile": side("a.py"),
        "secondFile": side("b.py", 20, 28),
    }
    return base | changes


def report(tmp_path: Path, *entries: dict[str, object]) -> Path:
    path = tmp_path / "jscpd-report.json"
    path.write_text(json.dumps({"duplicates": list(entries), "statistics": {}}), encoding="utf-8")
    return path


def test_a_clone_is_read_with_both_sides(tmp_path: Path) -> None:
    clones = read_clones(report(tmp_path, entry()))

    assert clones == (
        Clone(
            first=CloneSide("a.py", 1, 9),
            second=CloneSide("b.py", 20, 28),
            lines=9,
            tokens=60,
            is_new=False,
            kind="exact",
            format="python",
        ),
    )


def test_a_report_without_clones_is_empty_not_unreadable(tmp_path: Path) -> None:
    assert read_clones(report(tmp_path)) == ()


def test_only_a_true_is_new_marks_a_new_clone(tmp_path: Path) -> None:
    clones = read_clones(
        report(tmp_path, entry(isNew=True), entry(isNew=False), entry(isNew="true"), _drop("isNew"))
    )

    assert clones is not None
    assert [clone.is_new for clone in clones] == [True, False, False, False]


def test_the_line_comes_from_the_location_when_there_is_one(tmp_path: Path) -> None:
    first = side("a.py", 100, 200, located=False)
    first["startLoc"] = {"line": 3, "column": 1, "position": 100}
    first["endLoc"] = {"line": 12, "column": 1, "position": 200}

    clones = read_clones(report(tmp_path, entry(firstFile=first)))

    assert clones is not None
    assert clones[0].first == CloneSide("a.py", 3, 12)


def test_the_line_falls_back_to_start_and_end(tmp_path: Path) -> None:
    clones = read_clones(report(tmp_path, entry(firstFile=side("a.py", 4, 8, located=False))))

    assert clones is not None
    assert clones[0].first == CloneSide("a.py", 4, 8)


def test_a_windows_name_gets_forward_slashes_and_no_dot_prefix(tmp_path: Path) -> None:
    clones = read_clones(report(tmp_path, entry(firstFile=side(".\\src\\a.py"))))

    assert clones is not None
    assert clones[0].first.path == "src/a.py"


def test_a_clone_kind_is_kept(tmp_path: Path) -> None:
    clones = read_clones(report(tmp_path, entry(kind="renamed")))

    assert clones is not None
    assert clones[0].kind == "renamed"


def test_a_missing_kind_is_exact(tmp_path: Path) -> None:
    clones = read_clones(report(tmp_path, _drop("kind")))

    assert clones is not None
    assert clones[0].kind == "exact"


def _drop(key: str) -> dict[str, object]:
    return {k: v for k, v in entry().items() if k != key}


@pytest.mark.parametrize("missing", ["format", "lines", "tokens", "firstFile", "secondFile"])
def test_a_clone_without_a_required_field_is_unreadable(tmp_path: Path, missing: str) -> None:
    assert read_clones(report(tmp_path, _drop(missing))) is None


@pytest.mark.parametrize("field", ["lines", "tokens"])
@pytest.mark.parametrize("value", ["9", 9.5, True, None])
def test_a_size_that_is_not_a_whole_number_is_unreadable(
    tmp_path: Path, field: str, value: object
) -> None:
    assert read_clones(report(tmp_path, entry(**{field: value}))) is None


def test_a_side_that_is_not_an_object_is_unreadable(tmp_path: Path) -> None:
    assert read_clones(report(tmp_path, entry(firstFile="a.py"))) is None


def test_a_side_without_a_name_is_unreadable(tmp_path: Path) -> None:
    nameless = {"start": 1, "end": 2}

    assert read_clones(report(tmp_path, entry(firstFile=nameless))) is None


@pytest.mark.parametrize("text", ["", "not json", "[]", "{}", '{"duplicates": 3}'])
def test_a_file_that_is_not_a_report_is_unreadable(tmp_path: Path, text: str) -> None:
    path = tmp_path / "jscpd-report.json"
    path.write_text(text, encoding="utf-8")

    assert read_clones(path) is None


def test_a_missing_file_is_unreadable(tmp_path: Path) -> None:
    assert read_clones(tmp_path / "jscpd-report.json") is None
