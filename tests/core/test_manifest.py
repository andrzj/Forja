import hashlib
import os
import sys
from pathlib import Path

import pytest

from forja.core.manifest import (
    EntryKind,
    Manifest,
    ManifestEntry,
    ViolationKind,
    build_manifest,
    diff_manifests,
    find_violations,
)


def _write(root: Path, name: str, data: bytes = b"x") -> None:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def test_manifest_lists_files_with_posix_paths_and_ignores_empty_directories(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "a.txt")
    _write(tmp_path, "pkg/b.txt")
    (tmp_path / "empty").mkdir()

    manifest = build_manifest(tmp_path)

    assert sorted(manifest.entries) == ["a.txt", "pkg/b.txt"]
    assert all(e.kind is EntryKind.FILE for e in manifest.entries.values())


def test_digest_depends_on_content_and_path_but_not_on_creation_order(tmp_path: Path) -> None:
    first, second = tmp_path / "first", tmp_path / "second"
    for name in ("a", "b", "c"):
        _write(first, name, name.encode())
    for name in ("c", "a", "b"):
        _write(second, name, name.encode())
    assert build_manifest(first).digest() == build_manifest(second).digest()

    _write(second, "b", b"changed")
    assert build_manifest(first).digest() != build_manifest(second).digest()

    renamed = tmp_path / "renamed"
    for name, data in (("a", b"a"), ("b2", b"b"), ("c", b"c")):
        _write(renamed, name, data)
    assert build_manifest(first).digest() != build_manifest(renamed).digest()


def test_line_endings_are_not_normalized(tmp_path: Path) -> None:
    _write(tmp_path / "lf", "f", b"a\nb\n")
    _write(tmp_path / "crlf", "f", b"a\r\nb\r\n")

    assert build_manifest(tmp_path / "lf").digest() != build_manifest(tmp_path / "crlf").digest()


def test_top_level_exclusion_applies_only_at_the_top(tmp_path: Path) -> None:
    _write(tmp_path, ".git", b"gitdir: elsewhere")
    _write(tmp_path, "src/.git", b"nested stays")

    manifest = build_manifest(tmp_path, exclude={".git"})

    assert sorted(manifest.entries) == ["src/.git"]


def test_diff_reports_created_modified_and_removed_and_a_rename_as_remove_plus_create(
    tmp_path: Path,
) -> None:
    for name in ("keep", "edit", "gone", "old"):
        _write(tmp_path / "before", name, name.encode())
    for name, data in (("keep", b"keep"), ("edit", b"EDIT"), ("new", b"old")):
        _write(tmp_path / "after", name, data)

    result = diff_manifests(build_manifest(tmp_path / "before"), build_manifest(tmp_path / "after"))

    assert result.created == ("new",)
    assert result.modified == ("edit",)
    assert result.removed == ("gone", "old")
    assert not result.is_empty


def test_identical_trees_have_an_empty_diff(tmp_path: Path) -> None:
    _write(tmp_path / "one", "f", b"same")
    _write(tmp_path / "two", "f", b"same")

    assert diff_manifests(
        build_manifest(tmp_path / "one"), build_manifest(tmp_path / "two")
    ).is_empty


@pytest.mark.skipif(sys.platform == "win32", reason="Windows has no execute bit")
def test_execute_bit_is_part_of_the_manifest(tmp_path: Path) -> None:
    _write(tmp_path / "plain", "run.sh", b"#!/bin/sh")
    _write(tmp_path / "exec", "run.sh", b"#!/bin/sh")
    os.chmod(tmp_path / "exec" / "run.sh", 0o755)

    assert build_manifest(tmp_path / "plain").digest() != build_manifest(tmp_path / "exec").digest()


def _symlink(link: Path, target: str) -> bool:
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        return False
    return True


def test_symlinks_are_recorded_not_followed(tmp_path: Path) -> None:
    _write(tmp_path / "outside", "secret", b"secret")
    root = tmp_path / "root"
    root.mkdir()
    if not _symlink(root / "link", str(tmp_path / "outside")):
        pytest.skip("symlinks not available")

    manifest = build_manifest(root)

    assert list(manifest.entries) == ["link"]
    assert manifest.entries["link"].kind is EntryKind.SYMLINK


def _entry(path: str, kind: EntryKind = EntryKind.FILE) -> ManifestEntry:
    return ManifestEntry(path, kind, "0" * 64, False)


def test_symlink_is_a_violation() -> None:
    manifest = Manifest({"link": _entry("link", EntryKind.SYMLINK), "ok": _entry("ok")})

    violations = find_violations(manifest, destination_root=Path("/dest"))

    assert [(v.kind, v.path) for v in violations] == [(ViolationKind.SYMLINK, "link")]


def test_names_that_differ_only_by_case_are_violations_for_both_paths() -> None:
    manifest = Manifest({"Readme.md": _entry("Readme.md"), "README.md": _entry("README.md")})

    violations = find_violations(manifest, destination_root=Path("/dest"))

    assert sorted((v.kind, v.path) for v in violations) == [
        (ViolationKind.CASE_COLLISION, "README.md"),
        (ViolationKind.CASE_COLLISION, "Readme.md"),
    ]


def test_path_too_long_for_windows_counts_the_destination_root() -> None:
    root = Path("C:/" + "r" * 100)
    short, long = "a" * 100, "b" * 200
    manifest = Manifest({short: _entry(short), long: _entry(long)})

    violations = find_violations(manifest, destination_root=root)

    assert [(v.kind, v.path) for v in violations] == [(ViolationKind.PATH_TOO_LONG, long)]


def test_clean_manifest_has_no_violations() -> None:
    manifest = Manifest({"a/b.txt": _entry("a/b.txt")})

    assert find_violations(manifest, destination_root=Path("/dest")) == []


# -- exact forms -------------------------------------------------------------------------------


def test_the_digest_is_the_sha256_of_this_canonical_form() -> None:
    # Written out: the digest is compared with a stored one when a resumed run decides whether a
    # copy is complete, so its form may not drift between versions.
    sha_a, sha_b = "a" * 64, "b" * 64
    manifest = Manifest(
        {
            "z/é.txt": ManifestEntry("z/é.txt", EntryKind.FILE, sha_b, True),
            "a.txt": ManifestEntry("a.txt", EntryKind.FILE, sha_a, False),
        }
    )
    accent = r"\u00e9"  # JSON spells a non-ASCII character as an escape
    canonical = (
        '[["a.txt","file","'
        + sha_a
        + '",false],["z/'
        + accent
        + '.txt","file","'
        + sha_b
        + '",true]]'
    )

    assert manifest.digest() == hashlib.sha256(canonical.encode("ascii")).hexdigest()


def test_a_file_is_recorded_with_its_content_hash(tmp_path: Path) -> None:
    _write(tmp_path, "a.txt", b"hello")

    entry = build_manifest(tmp_path).entries["a.txt"]

    assert entry == ManifestEntry(
        "a.txt", EntryKind.FILE, hashlib.sha256(b"hello").hexdigest(), False
    )


def test_a_symlink_is_recorded_by_the_hash_of_where_it_points(tmp_path: Path) -> None:
    if not _symlink(tmp_path / "link", "target.txt"):
        pytest.skip("symlinks not available")

    entry = build_manifest(tmp_path).entries["link"]

    assert entry == ManifestEntry(
        "link", EntryKind.SYMLINK, hashlib.sha256(b"target.txt").hexdigest(), False
    )


@pytest.mark.skipif(sys.platform == "win32", reason="needs a name that is not valid UTF-8")
def test_a_symlink_whose_target_is_not_valid_text_is_still_recorded(tmp_path: Path) -> None:
    os.symlink(b"\xff-target", bytes(tmp_path / "link"))

    entry = build_manifest(tmp_path).entries["link"]

    assert entry.sha256 == hashlib.sha256(b"\xff-target").hexdigest()


def test_a_symlink_to_a_directory_is_one_entry_and_the_directory_is_not_entered(
    tmp_path: Path,
) -> None:
    _write(tmp_path / "real", "inside.txt")
    if not _symlink(tmp_path / "alias", "real"):
        pytest.skip("symlinks not available")

    assert sorted(build_manifest(tmp_path).entries) == ["alias", "real/inside.txt"]


@pytest.mark.skipif(sys.platform == "win32", reason="Windows has no execute bit")
def test_the_execute_bit_is_read_where_the_file_system_has_one(tmp_path: Path) -> None:
    _write(tmp_path, "run.sh")
    os.chmod(tmp_path / "run.sh", 0o755)
    _write(tmp_path, "data.txt")

    entries = build_manifest(tmp_path).entries

    assert entries["run.sh"].executable is True
    assert entries["data.txt"].executable is False


def test_where_the_file_system_has_no_execute_bit_no_file_is_executable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write(tmp_path, "run.sh")
    os.chmod(tmp_path / "run.sh", 0o755)
    monkeypatch.setattr("forja.core.manifest._HAS_EXECUTE_BIT", False)

    assert build_manifest(tmp_path).entries["run.sh"].executable is False


def test_the_words_of_each_violation(tmp_path: Path) -> None:
    root = Path("/dest")
    manifest = Manifest(
        {
            "link": _entry("link", EntryKind.SYMLINK),
            "Readme.md": _entry("Readme.md"),
            "README.md": _entry("README.md"),
        }
    )

    details = {(v.kind, v.path): v.detail for v in find_violations(manifest, destination_root=root)}

    assert details == {
        (ViolationKind.SYMLINK, "link"): "symlink may point outside the working copy",
        (ViolationKind.CASE_COLLISION, "Readme.md"): "differs only by case from: README.md",
        (ViolationKind.CASE_COLLISION, "README.md"): "differs only by case from: Readme.md",
    }


def test_a_path_exactly_at_the_limit_is_fine_and_one_more_is_not() -> None:
    root = Path("/dest")  # 5 characters, plus one separator
    at_limit, over = "a" * 10, "b" * 11
    manifest = Manifest({at_limit: _entry(at_limit), over: _entry(over)})

    violations = find_violations(manifest, destination_root=root, max_path_length=16)

    assert [(v.kind, v.path, v.detail) for v in violations] == [
        (ViolationKind.PATH_TOO_LONG, over, "17 characters under the destination exceeds 16")
    ]


def test_a_collision_between_three_names_lists_the_other_two() -> None:
    names = ("A.txt", "a.txt", "a.TXT")
    manifest = Manifest({n: _entry(n) for n in names})

    details = {v.path: v.detail for v in find_violations(manifest, destination_root=Path("/d"))}

    assert details["A.txt"] == "differs only by case from: a.TXT, a.txt"


@pytest.mark.skipif(sys.platform != "win32", reason="junctions exist on Windows")
def test_a_junction_is_recorded_like_a_link_and_never_followed(tmp_path: Path) -> None:
    import _winapi  # noqa: PLC0415

    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("not ours\n", encoding="utf-8")
    root = tmp_path / "root"
    root.mkdir()
    _winapi.CreateJunction(str(outside), str(root / "jn"))  # type: ignore[attr-defined]

    entries = build_manifest(root).entries

    assert list(entries) == ["jn"]
    assert entries["jn"].kind is EntryKind.SYMLINK
