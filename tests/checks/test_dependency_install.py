"""Gate 2: new dependencies are proven to exist, then installed, before the checks run."""

import asyncio
from pathlib import Path
from typing import Any

from forja.checks.changes import Change, ChangeKind, Changes
from forja.checks.dependency_install import (
    DependencyInstallCheck,
    install_findings,
    requirements_of,
)
from forja.checks.new_dependency import manifests_of
from forja.checks.registries import Response
from forja.core.gates import Approved, Finding, GateInput
from forja.core.gates.models import Rejected
from forja.languages.python import PythonAdapter

MANIFEST = "requirements.txt"
PYPROJECT = "pyproject.toml"


async def get(url: str) -> Response | None:
    if "ghost" in url:
        return Response(404, b"")
    if "offline" in url:
        return None
    return Response(
        200, b'{"releases": {"1.0": [{"upload_time_iso_8601": "2020-01-01T00:00:00Z"}]}}'
    )


class Installer:
    def __init__(self, failure: str | None = None) -> None:
        self.calls: list[frozenset[str]] = []
        self.failure = failure

    async def __call__(self, requirements: frozenset[str]) -> str | None:
        self.calls.append(requirements)
        return self.failure


def run(
    tmp_path: Path,
    text: str,
    before: str = "",
    *,
    installer: Installer,
    name: str = MANIFEST,
    kind: ChangeKind = ChangeKind.MODIFIED,
) -> list[str]:
    (tmp_path / name).write_text(text, encoding="utf-8")
    adapters = [PythonAdapter()]
    found = asyncio.run(
        install_findings(
            tmp_path,
            Changes((Change(kind, name),), 0, ()),
            {name: before},
            manifests_of(adapters),
            requirements_of(adapters),
            installer,
            get,
        )
    )
    return [f.message for f in found]


def test_the_requirement_of_a_new_name_is_installed_whole(tmp_path: Path) -> None:
    installer = Installer()

    assert run(tmp_path, "flask\nrequests>=2.0\n", "flask\n", installer=installer) == []
    assert installer.calls == [frozenset({"requests>=2.0"})]


def test_nothing_is_installed_when_no_name_is_new(tmp_path: Path) -> None:
    installer = Installer()

    assert run(tmp_path, "flask\n", "flask\n", installer=installer) == []
    assert installer.calls == []


def test_the_requirement_is_matched_to_its_name_whatever_the_spelling(tmp_path: Path) -> None:
    installer = Installer()

    assert run(tmp_path, "Typing_Extensions>=4\nflask\n", "flask\n", installer=installer) == []
    assert installer.calls == [frozenset({"Typing_Extensions>=4"})]


def test_the_dependencies_of_a_pyproject_are_installed(tmp_path: Path) -> None:
    installer = Installer()
    text = '[project]\nname = "x"\ndependencies = ["flask", "slugify>=1"]\n'
    before = '[project]\nname = "x"\ndependencies = ["flask"]\n'

    assert run(tmp_path, text, before, installer=installer, name=PYPROJECT) == []
    assert installer.calls == [frozenset({"slugify>=1"})]


def test_a_name_the_registry_does_not_list_is_never_installed(tmp_path: Path) -> None:
    installer = Installer()

    found = run(tmp_path, "flask\nghost\n", "flask\n", installer=installer)

    assert found == ["ghost does not exist in the PyPI registry"]
    assert installer.calls == []


def test_a_registry_that_does_not_answer_installs_nothing(tmp_path: Path) -> None:
    installer = Installer()

    found = run(tmp_path, "offline\n", installer=installer, kind=ChangeKind.ADDED)

    assert found == ["offline could not be checked in the PyPI registry"]
    assert installer.calls == []


def test_a_failed_installation_says_why_and_where(tmp_path: Path) -> None:
    installer = Installer("pip failed (1): no matching distribution")

    found = run(tmp_path, "a\nb\n", "", installer=installer)

    assert found == ["installing a, b failed: pip failed (1): no matching distribution"]


def test_a_manifest_of_another_language_is_left_alone(tmp_path: Path) -> None:
    installer = Installer()

    assert (
        run(
            tmp_path,
            '{"dependencies": {"ghost": "1"}}',
            "",
            installer=installer,
            name="package.json",
        )
        == []
    )
    assert installer.calls == []


def test_the_check_rejects_with_its_findings_or_approves_when_it_has_none() -> None:
    data: Any = GateInput(Path("."), "head", "t", "s", "a")
    finding = Finding(message="x does not exist", target=MANIFEST)

    rejected = asyncio.run(DependencyInstallCheck((finding,)).evaluate(data))
    approved = asyncio.run(DependencyInstallCheck(()).evaluate(data))

    assert isinstance(rejected, Rejected) and rejected.findings == (finding,)
    assert isinstance(approved, Approved)
    assert DependencyInstallCheck(()).gate == 2
