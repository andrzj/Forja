import os
from pathlib import Path

import pytest

from forja.cli.doctor import _where
from forja.toolchain.install import find_installed
from forja.toolchain.manifest import Manifest
from forja.toolchain.resolve import (
    installed_by_forja,
    installed_directories,
    with_installed_tools,
)
from tests.toolchain.test_install import HERE, Origin, manifest_for, run, zip_bytes

SEP = os.pathsep


def installed(tmp_path: Path, kind: str = "zip") -> tuple[Manifest, Path]:
    content = zip_bytes({"bin/tool": b"run"})
    manifest = manifest_for(content)
    root = tmp_path / "tools"
    run(manifest, "tool", root, target=HERE, fetch=Origin(content))
    return manifest, root


def test_nothing_installed_finds_nothing(tmp_path: Path) -> None:
    manifest = manifest_for(zip_bytes({"bin/tool": b"run"}))

    assert find_installed(manifest, "tool", tmp_path / "tools", target=HERE) is None
    assert installed_directories(manifest, tmp_path / "tools", target=HERE) == ([], [])


def test_an_installed_tool_is_found_where_it_was_put(tmp_path: Path) -> None:
    manifest, root = installed(tmp_path)

    found = find_installed(manifest, "tool", root, target=HERE)

    assert found is not None
    assert found.executable == root / "tool" / "1.2.3" / "bin" / "tool"
    assert found.already


def test_a_half_installed_tool_is_not_found(tmp_path: Path) -> None:
    manifest, root = installed(tmp_path)
    (root / "tool" / "1.2.3" / ".forja-installed").unlink()

    assert find_installed(manifest, "tool", root, target=HERE) is None


def test_the_folder_of_the_executable_goes_in_front_of_the_path(tmp_path: Path) -> None:
    manifest, root = installed(tmp_path)
    folder = str(root / "tool" / "1.2.3" / "bin")

    result = with_installed_tools(
        {"PATH": f"one{SEP}two"}, manifest=manifest, root=root, target=HERE
    )

    assert result["PATH"] == f"{folder}{SEP}one{SEP}two"


def test_the_rest_of_the_environment_is_kept_and_the_input_is_not_changed(tmp_path: Path) -> None:
    manifest, root = installed(tmp_path)
    environ = {"PATH": "one", "HOME": "h"}

    result = with_installed_tools(environ, manifest=manifest, root=root, target=HERE)

    assert result["HOME"] == "h"
    assert environ == {"PATH": "one", "HOME": "h"}


def test_applying_it_twice_changes_nothing(tmp_path: Path) -> None:
    manifest, root = installed(tmp_path)

    once = with_installed_tools({"PATH": "one"}, manifest=manifest, root=root, target=HERE)
    twice = with_installed_tools(once, manifest=manifest, root=root, target=HERE)

    assert twice == once


def test_the_path_key_keeps_its_spelling(tmp_path: Path) -> None:
    manifest, root = installed(tmp_path)

    result = with_installed_tools({"Path": "one"}, manifest=manifest, root=root, target=HERE)

    assert list(result) == ["Path"]
    assert result["Path"].endswith(f"{SEP}one")


def test_an_environment_without_a_path_gets_one(tmp_path: Path) -> None:
    manifest, root = installed(tmp_path)

    result = with_installed_tools({}, manifest=manifest, root=root, target=HERE)

    assert result["PATH"] == str(root / "tool" / "1.2.3" / "bin")


def test_without_installed_tools_the_path_is_the_same(tmp_path: Path) -> None:
    manifest = manifest_for(zip_bytes({"bin/tool": b"run"}))

    result = with_installed_tools(
        {"PATH": "one"}, manifest=manifest, root=tmp_path / "tools", target=HERE
    )

    assert result == {"PATH": "one"}


def test_a_tool_in_a_virtual_environment_goes_after_the_path(tmp_path: Path) -> None:
    manifest, root = installed(tmp_path)
    wheel = manifest.model_copy(
        update={
            "tools": (
                manifest.tools[0].model_copy(
                    update={
                        "artifacts": {
                            HERE: manifest.tools[0]
                            .artifacts[HERE]
                            .model_copy(update={"kind": "wheel"})
                        }
                    }
                ),
            )
        }
    )

    result = with_installed_tools({"PATH": "one"}, manifest=wheel, root=root, target=HERE)

    assert result["PATH"] == f"one{SEP}{root / 'tool' / '1.2.3' / 'bin'}"


def test_the_tools_of_the_forja_home_are_the_default_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest = manifest_for(zip_bytes({"bin/tool": b"run"}))
    home = tmp_path / "home"
    content = zip_bytes({"bin/tool": b"run"})
    run(manifest, "tool", home / "tools", target=HERE, fetch=Origin(content))

    result = with_installed_tools(
        {"PATH": "one", "FORJA_HOME": str(home)}, manifest=manifest, target=HERE
    )

    assert result["PATH"].startswith(str(home / "tools" / "tool" / "1.2.3" / "bin"))


def test_a_file_inside_the_tools_folder_is_the_forjas(tmp_path: Path) -> None:
    root = tmp_path / "tools"
    (root / "go").mkdir(parents=True)
    inside = root / "go" / "go.exe"
    inside.write_bytes(b"")
    outside = tmp_path / "go.exe"
    outside.write_bytes(b"")

    assert installed_by_forja(inside, root)
    assert not installed_by_forja(outside, root)
    assert not installed_by_forja(root, root)


def test_the_doctor_says_where_a_found_tool_is(tmp_path: Path) -> None:
    home = tmp_path / "home"
    folder = home / "tools" / "go" / "1.0" / "bin"
    folder.mkdir(parents=True)
    names = ("go.exe", "go") if os.name == "nt" else ("go",)
    for name in names:
        executable = folder / name
        executable.write_bytes(b"")
        executable.chmod(0o755)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    for name in names:
        other = elsewhere / name
        other.write_bytes(b"")
        other.chmod(0o755)

    ours = _where("go", {"PATH": str(folder), "FORJA_HOME": str(home)})
    theirs = _where("go", {"PATH": str(elsewhere), "FORJA_HOME": str(home)})

    assert ours.startswith("go instalado pela Forja (") and str(folder) in ours
    assert theirs == "go no PATH"
