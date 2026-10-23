"""The new-dependency check: what the attempt added is looked up, judged with fake registries."""

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from forja.checks.changes import Change, ChangeKind, Changes
from forja.checks.new_dependency import (
    DEFAULT_MIN_AGE_DAYS,
    MAX_LOOKUPS,
    Declared,
    NewDependencyCheck,
    threshold,
)
from forja.checks.registries import Response
from forja.core.gates import Approved, GateInput, GateResult, Inconclusive
from forja.core.gates.models import Rejected

NOW = datetime(2026, 10, 22, tzinfo=UTC)
MANIFEST = "package.json"


def manifests(path: str, text: str) -> Declared | None:
    """A stand-in manifest format: one name per line, in files called package.json."""
    if not path.endswith(MANIFEST):
        return None
    return Declared("typescript", "npm", frozenset(text.split()))


def registry(*, created: str = "2020-01-01T00:00:00Z", downloads: int = 5000) -> Any:
    async def get(url: str) -> Response | None:
        name = url.rsplit("/", 1)[-1]
        if name == "ghost":
            return Response(404, b"")
        if name == "offline":
            return None
        if "downloads" in url:
            return Response(200, f'{{"downloads": {downloads}}}'.encode())
        return Response(200, f'{{"time": {{"created": "{created}"}}}}'.encode())

    return get


def judge(
    tmp_path: Path,
    now_text: str,
    before: str | None = "",
    *,
    get: Any = None,
    values: dict[str, Any] | None = None,
    path: str = MANIFEST,
) -> GateResult:
    (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / path).write_text(now_text, encoding="utf-8")
    change = Change(ChangeKind.ADDED if before is None else ChangeKind.MODIFIED, path)
    check = NewDependencyCheck(
        tmp_path,
        Changes((change,), 0, ()),
        {} if before is None else {path: before},
        manifests,
        get or registry(),
        lambda: NOW,
    )
    return asyncio.run(
        check.evaluate(GateInput(tmp_path, "c" * 40, "t", "s", "a", values=values or {}))
    )


def described(result: GateResult) -> list[str]:
    assert isinstance(result, Rejected)
    return [f.message for f in result.findings]


def test_nothing_new_in_a_manifest_means_nothing_is_looked_up(tmp_path: Path) -> None:
    async def never(url: str) -> Response | None:
        raise AssertionError(url)

    assert judge(tmp_path, "a b\n", "a b c\n", get=never) == Approved()


def test_a_file_that_is_not_a_manifest_is_left_alone(tmp_path: Path) -> None:
    assert judge(tmp_path, "x\n", "", path="notes.txt") == Approved()


def test_a_deleted_manifest_is_not_read(tmp_path: Path) -> None:
    check = NewDependencyCheck(
        tmp_path, Changes((Change(ChangeKind.DELETED, MANIFEST),), 0, ()), {}, manifests
    )

    assert asyncio.run(check.evaluate(GateInput(tmp_path, "c" * 40, "t", "s", "a"))) == Approved()


def test_a_known_old_used_package_is_approved(tmp_path: Path) -> None:
    assert judge(tmp_path, "a left-pad\n", "a\n") == Approved()


def test_a_new_manifest_has_nothing_to_compare_with(tmp_path: Path) -> None:
    assert described(judge(tmp_path, "ghost\n", None)) == [
        "ghost does not exist in the npm registry"
    ]


def test_a_package_that_does_not_exist_is_rejected_by_name(tmp_path: Path) -> None:
    result = judge(tmp_path, "left-pad ghost\n", "left-pad\n")

    assert described(result) == ["ghost does not exist in the npm registry"]
    assert isinstance(result, Rejected) and result.findings[0].target == MANIFEST


def test_a_package_younger_than_the_minimum_age_is_rejected(tmp_path: Path) -> None:
    result = judge(tmp_path, "fresh\n", "", get=registry(created="2026-10-10T00:00:00Z"))

    assert described(result) == [
        f"fresh was first published 12 day(s) ago (minimum {DEFAULT_MIN_AGE_DAYS})"
    ]


def test_a_package_with_few_downloads_is_rejected(tmp_path: Path) -> None:
    result = judge(tmp_path, "tiny\n", "", get=registry(downloads=3))

    assert described(result) == ["tiny has 3 download(s) (minimum 100)"]


def test_the_limits_are_the_policys_per_language(tmp_path: Path) -> None:
    values = {"thresholds": {"typescript": {"min_age_days": 5000, "min_downloads": 0}}}

    result = judge(tmp_path, "old\n", "", values=values)

    assert described(result)[0].endswith("(minimum 5000)")
    relaxed = {"thresholds": {"typescript": {"min_age_days": 0, "min_downloads": 0}}}
    assert (
        judge(
            tmp_path,
            "old\n",
            "",
            get=registry(created="2026-10-22T00:00:00Z", downloads=0),
            values=relaxed,
        )
        == Approved()
    )


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        ({}, 30),
        ({"thresholds": {"go": {"min_age_days": 9}}}, 30),
        ({"thresholds": {"typescript": {"min_age_days": 9}}}, 9),
        ({"thresholds": {"typescript": {"min_age_days": 0}}}, 0),
        ({"thresholds": {"typescript": {"min_age_days": -1}}}, 30),
        ({"thresholds": {"typescript": {"min_age_days": "9"}}}, 30),
        ({"thresholds": "x"}, 30),
    ],
)
def test_the_threshold_comes_from_the_policy_or_the_default(
    values: dict[str, Any], expected: int
) -> None:
    data = GateInput(Path("."), "c" * 40, "t", "s", "a", values=values)

    assert threshold(data, "typescript", "min_age_days", 30) == expected


def test_a_registry_that_does_not_answer_is_inconclusive_never_a_pass(tmp_path: Path) -> None:
    result = judge(tmp_path, "offline\n", "")

    assert isinstance(result, Inconclusive)
    assert result.detail == "new_dependency: could not verify offline"


def test_a_package_that_is_missing_wins_over_one_that_could_not_be_checked(
    tmp_path: Path,
) -> None:
    assert isinstance(judge(tmp_path, "offline ghost\n", ""), Rejected)


def test_too_many_new_names_are_not_looked_up_one_by_one(tmp_path: Path) -> None:
    names = "\n".join(f"p{n}" for n in range(MAX_LOOKUPS + 1))

    result = judge(tmp_path, names, "")

    assert isinstance(result, Inconclusive)
    assert (
        result.detail == f"new_dependency: {MAX_LOOKUPS + 1} new dependencies (limit {MAX_LOOKUPS})"
    )


def test_a_manifest_that_cannot_be_read_is_never_taken_for_an_empty_one(tmp_path: Path) -> None:
    def broken(path: str, text: str) -> Declared | None:
        raise ValueError("not valid JSON")

    (tmp_path / MANIFEST).write_text("{", encoding="utf-8")
    change = Change(ChangeKind.MODIFIED, MANIFEST)
    check = NewDependencyCheck(tmp_path, Changes((change,), 0, ()), {MANIFEST: "{}"}, broken)

    result = asyncio.run(check.evaluate(GateInput(tmp_path, "c" * 40, "t", "s", "a")))

    assert isinstance(result, Inconclusive)
    assert result.detail == "new_dependency: could not verify package.json (unreadable)"


def test_a_registry_that_cannot_date_the_package_is_inconclusive(tmp_path: Path) -> None:
    def go_manifest(path: str, text: str) -> Declared | None:
        return Declared("go", "Go", frozenset(text.split()))

    async def listed(url: str) -> Response | None:
        return Response(200, b"v1.0.0\n")

    (tmp_path / "go.mod").write_text("example.com/m", encoding="utf-8")
    change = Change(ChangeKind.ADDED, "go.mod")
    check = NewDependencyCheck(tmp_path, Changes((change,), 0, ()), {}, go_manifest, listed)

    result = asyncio.run(check.evaluate(GateInput(tmp_path, "c" * 40, "t", "s", "a")))

    assert isinstance(result, Inconclusive)
    assert result.detail == "new_dependency: could not verify example.com/m"


def test_a_manifest_that_is_not_text_is_unreadable_but_another_binary_file_is_not(
    tmp_path: Path,
) -> None:
    (tmp_path / MANIFEST).write_bytes(b"\xff\xfe{\x00}\x00")
    (tmp_path / "logo.png").write_bytes(b"\x89PNG\xff")
    changes = Changes(
        (Change(ChangeKind.ADDED, "logo.png"), Change(ChangeKind.ADDED, MANIFEST)), 0, ()
    )
    check = NewDependencyCheck(tmp_path, changes, {}, manifests)

    result = asyncio.run(check.evaluate(GateInput(tmp_path, "c" * 40, "t", "s", "a")))

    assert isinstance(result, Inconclusive)
    assert result.detail == "new_dependency: could not verify package.json (unreadable)"
    only_image = NewDependencyCheck(tmp_path, Changes(changes.files[:1], 0, ()), {}, manifests)
    assert (
        asyncio.run(only_image.evaluate(GateInput(tmp_path, "c" * 40, "t", "s", "a"))) == Approved()
    )


def test_exactly_the_limit_of_new_names_is_still_looked_up(tmp_path: Path) -> None:
    names = "\n".join(f"p{n}" for n in range(MAX_LOOKUPS))

    assert judge(tmp_path, names, "") == Approved()


def test_the_clock_is_the_real_one_unless_a_test_gives_another(tmp_path: Path) -> None:
    (tmp_path / MANIFEST).write_text("left-pad", encoding="utf-8")
    check = NewDependencyCheck(
        tmp_path,
        Changes((Change(ChangeKind.ADDED, MANIFEST),), 0, ()),
        {},
        manifests,
        registry(),
    )

    assert asyncio.run(check.evaluate(GateInput(tmp_path, "c" * 40, "t", "s", "a"))) == Approved()


def test_a_file_that_cannot_be_read_and_whose_name_does_not_parse_empty_is_a_manifest(
    tmp_path: Path,
) -> None:
    def picky(path: str, text: str) -> Declared | None:
        if path.endswith(MANIFEST):
            raise ValueError("an empty manifest is not valid")
        return None

    (tmp_path / MANIFEST).write_bytes(b"\xff\xfe\x00")
    (tmp_path / "logo.png").write_bytes(b"\x89PNG\xff")
    changes = Changes(
        (Change(ChangeKind.ADDED, "logo.png"), Change(ChangeKind.ADDED, MANIFEST)), 0, ()
    )
    check = NewDependencyCheck(tmp_path, changes, {}, picky)

    result = asyncio.run(check.evaluate(GateInput(tmp_path, "c" * 40, "t", "s", "a")))

    assert isinstance(result, Inconclusive)
    assert result.detail == "new_dependency: could not verify package.json (unreadable)"
