"""Which artifact the platform running now downloads."""

import sys

import pytest

from forja.toolchain.load import (
    NoArtifactForPlatform,
    UnknownTool,
    UnsupportedPlatform,
    artifact_for,
    current_platform,
    find_tool,
    parse_manifest,
)
from forja.toolchain.manifest import Platform
from tests.toolchain.test_manifest import VALID


@pytest.mark.parametrize(
    "system, machine, expected",
    [
        ("win32", "AMD64", "windows-x64"),
        ("win32", "x86_64", "windows-x64"),
        ("linux", "x86_64", "linux-x64"),
        ("linux", "AMD64", "linux-x64"),
        ("linux2", "x86_64", "linux-x64"),
    ],
)
def test_the_supported_platforms(system: str, machine: str, expected: str) -> None:
    assert current_platform(system, machine) == expected


@pytest.mark.parametrize(
    "system, machine",
    [
        ("darwin", "arm64"),
        ("darwin", "x86_64"),
        ("win32", "ARM64"),
        ("linux", "aarch64"),
        ("freebsd14", "amd64"),
    ],
)
def test_other_platforms_are_refused(system: str, machine: str) -> None:
    with pytest.raises(UnsupportedPlatform) as raised:
        current_platform(system, machine)
    assert f"{system} {machine}" in str(raised.value)


def test_the_running_platform_is_the_default() -> None:
    if sys.platform in ("win32", "linux"):
        assert current_platform() in ("windows-x64", "linux-x64")


def test_the_artifact_of_a_platform_is_returned() -> None:
    artifact = artifact_for(parse_manifest(VALID), "gitleaks", "windows-x64")
    assert (artifact.kind, artifact.executable_path) == ("zip", "gitleaks.exe")


def test_a_platform_without_an_artifact_is_refused() -> None:
    target: Platform = "linux-x64"
    with pytest.raises(NoArtifactForPlatform) as raised:
        artifact_for(parse_manifest(VALID), "gitleaks", target)
    assert (raised.value.tool, raised.value.platform) == ("gitleaks", "linux-x64")
    assert "gitleaks" in str(raised.value) and "linux-x64" in str(raised.value)


def test_an_unknown_tool_is_refused() -> None:
    with pytest.raises(UnknownTool) as raised:
        artifact_for(parse_manifest(VALID), "git", "windows-x64")
    assert raised.value.name == "git" and "'git'" in str(raised.value)


def test_a_tool_is_found_by_name_among_several() -> None:
    second = VALID.split("\n", 2)[2].replace("gitleaks", "osv-scanner")
    manifest = parse_manifest(VALID + second)
    assert find_tool(manifest, "osv-scanner").name == "osv-scanner"
