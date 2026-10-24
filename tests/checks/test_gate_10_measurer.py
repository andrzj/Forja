"""Gate 10 inside the real pipeline: the three checks are judged for every attempt, with the
tools and registries the measurer was given (stand-ins here)."""

import sys
from pathlib import Path
from typing import Any

from forja.checks.registries import Response
from forja.core.gates import CheckSettings, Inconclusive, Mode, NotApplicable
from forja.core.gates.models import Rejected
from tests.checks.support import Scene, judge_with
from tests.core.idempotency.conftest import Repo, repo  # noqa: F401 - re-exported as a fixture

EVERY_CHECK = (
    "scope", "secrets", "format", "lint", "build", "tests", "mutation", "complexity", "crap",
    "pass_through", "module_depth", "sast", "dependency_audit", "new_dependency",
    "e2e", "test_data", "voice",
)  # fmt: skip
FAKE_SEMGREP = Path(__file__).with_name("fake_semgrep.py")
FAKE_OSV = Path(__file__).with_name("fake_osv_scanner.py")


async def no_such_package(url: str) -> Response | None:
    return Response(404, b"")


def scene_with(repo: Repo, tmp_path: Path, **gate_10: Any) -> Scene:  # noqa: F811
    """Every gate only observes, so that the scope gate (a manifest is not production code, and
    a refactoring may not touch it) does not stop the attempt before gate 10."""
    observing = {name: CheckSettings(Mode.OBSERVATION) for name in EVERY_CHECK}
    return Scene(repo, tmp_path / "scene", settings=observing, gate_10=gate_10)


def test_a_run_with_rules_calls_semgrep_on_what_the_attempt_changed(
    repo: Repo,  # noqa: F811
    tmp_path: Path,
) -> None:
    rules = tmp_path / "rules.yml"
    rules.write_text("rules", encoding="utf-8")
    scene = scene_with(
        repo,
        tmp_path,
        semgrep=(sys.executable, str(FAKE_SEMGREP)),
        semgrep_config=rules,
    )
    scene.write("src/sample/mod.py", "FAKE-FINDING\n")

    result = judge_with(scene, "sast")

    assert isinstance(result, Rejected)
    assert [f.target for f in result.findings] == ["src/sample/mod.py"]
    assert result.findings[0].message == "1 new fake-rule finding(s)"


def test_a_run_without_rules_does_not_run_the_sast_and_says_so(
    repo: Repo,  # noqa: F811
    tmp_path: Path,
) -> None:
    scene = scene_with(repo, tmp_path, semgrep=("no-such-semgrep-anywhere",))
    scene.write("src/sample/mod.py", "FAKE-FINDING\n")

    assert judge_with(scene, "sast") == NotApplicable(missing_capability="semgrep_config")


def test_a_new_vulnerability_in_a_lockfile_is_found_with_the_scanner_given(
    repo: Repo,  # noqa: F811
    tmp_path: Path,
) -> None:
    scene = scene_with(repo, tmp_path, osv_scanner=(sys.executable, str(FAKE_OSV)))
    scene.write("requirements.txt", "a 1 vulns=GHSA-1\n")

    result = judge_with(scene, "dependency_audit")

    assert isinstance(result, Rejected)
    assert result.findings[0].message == "new vulnerability GHSA-1 in a 1"


def test_the_forbidden_licenses_of_the_policy_are_compared_without_case(
    repo: Repo,  # noqa: F811
    tmp_path: Path,
) -> None:
    scene = scene_with(
        repo,
        tmp_path,
        osv_scanner=(sys.executable, str(FAKE_OSV)),
        forbidden_licenses=("GPL-3.0-Only",),
    )
    scene.write("requirements.txt", "a 1 licenses=gpl-3.0-only\n")

    result = judge_with(scene, "dependency_audit")

    assert isinstance(result, Rejected)
    assert result.findings[0].message == "forbidden license gpl-3.0-only in a 1"


def test_a_scanner_that_is_not_installed_is_inconclusive_not_a_pass(
    repo: Repo,  # noqa: F811
    tmp_path: Path,
) -> None:
    scene = scene_with(repo, tmp_path, osv_scanner=("no-such-osv-scanner-anywhere",))
    scene.write("requirements.txt", "a 1\n")

    assert isinstance(judge_with(scene, "dependency_audit"), Inconclusive)


def test_a_dependency_added_to_a_manifest_is_looked_up_in_the_registry_given(
    repo: Repo,  # noqa: F811
    tmp_path: Path,
) -> None:
    scene = scene_with(repo, tmp_path, registry_get=no_such_package)
    scene.write("requirements.txt", "ghost-package==1.0\n")

    result = judge_with(scene, "new_dependency")

    assert isinstance(result, Rejected)
    assert result.findings[0].message == "ghost-package does not exist in the PyPI registry"
    assert result.findings[0].target == "requirements.txt"


def test_a_change_that_touches_no_dependency_file_asks_nobody(
    repo: Repo,  # noqa: F811
    tmp_path: Path,
) -> None:
    async def never(url: str) -> Response | None:
        raise AssertionError(url)

    scene = scene_with(
        repo, tmp_path, registry_get=never, osv_scanner=("no-such-osv-scanner-anywhere",)
    )
    scene.write("src/sample/mod.py", "X = 1\n")

    assert judge_with(scene, "new_dependency").result == "approved"
    assert judge_with(scene, "dependency_audit").result == "approved"
