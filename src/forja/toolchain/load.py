"""Reads and validates the manifest, and answers which artifact the current platform downloads."""

import platform
import sys
import tomllib
from collections.abc import Sequence
from importlib import resources
from pathlib import Path

from pydantic import ValidationError

from forja.toolchain.manifest import Artifact, Manifest, Platform, Tool

MANIFEST_NAME = "manifest.toml"


class ManifestError(Exception):
    """The manifest cannot be used; ``problems`` lists everything wrong, with where."""

    def __init__(self, problems: Sequence[str]) -> None:
        self.problems = list(problems)
        super().__init__("invalid tool manifest:\n- " + "\n- ".join(self.problems))


class UnknownTool(Exception):
    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"the manifest has no tool {name!r}")


class UnsupportedPlatform(Exception):
    def __init__(self, system: str, machine: str) -> None:
        super().__init__(
            f"the Forja installs tools for Windows x64 and Linux x64, not {system} {machine}"
        )


class NoArtifactForPlatform(Exception):
    def __init__(self, tool: str, target: Platform) -> None:
        self.tool = tool
        self.platform = target
        super().__init__(f"the manifest has no artifact of {tool!r} for {target}")


def parse_manifest(text: str, source: str = MANIFEST_NAME) -> Manifest:
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        raise ManifestError([f"{source}: not valid TOML: {error}"]) from error
    try:
        return Manifest.model_validate(data)
    except ValidationError as error:
        raise ManifestError(
            [f"{source}: {'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in error.errors()]
        ) from error


def load_manifest(path: Path | None = None) -> Manifest:
    """The manifest shipped inside the package, or the one at ``path``."""
    if path is None:
        text = resources.files("forja.toolchain").joinpath(MANIFEST_NAME).read_text("utf-8")
        return parse_manifest(text)
    try:
        text = path.read_text("utf-8")
    except OSError as error:
        raise ManifestError([f"{path}: cannot be read: {error}"]) from error
    return parse_manifest(text, str(path))


def current_platform(system: str | None = None, machine: str | None = None) -> Platform:
    system = sys.platform if system is None else system
    machine = platform.machine() if machine is None else machine
    if machine.lower() in ("amd64", "x86_64"):
        if system == "win32":
            return "windows-x64"
        if system.startswith("linux"):
            return "linux-x64"
    raise UnsupportedPlatform(system, machine)


def find_tool(manifest: Manifest, name: str) -> Tool:
    for tool in manifest.tools:
        if tool.name == name:
            return tool
    raise UnknownTool(name)


def artifact_for(manifest: Manifest, name: str, target: Platform | None = None) -> Artifact:
    """The artifact of tool ``name`` for ``target`` (default: the platform running now)."""
    tool = find_tool(manifest, name)
    target = current_platform() if target is None else target
    artifact = tool.artifacts.get(target)
    if artifact is None:
        raise NoArtifactForPlatform(name, target)
    return artifact
