"""Gate 14 for the README: the documenter fixes what failed and touches nothing else."""

import asyncio
from pathlib import Path

from forja.checks.readme_gate import ReadmeCheck, read_readme, readme_path
from forja.core.gates import Approved, GateInput, GateResult, Rejected

FENCE = "`" * 3


def readme(build: str = "go build ./...", configuration: str = "None.") -> str:
    return "\n".join(
        [
            "# Sample",
            "",
            "A library.",
            "",
            "## Build",
            "",
            FENCE,
            build,
            FENCE,
            "",
            "## Tests",
            "",
            FENCE,
            "go test ./...",
            FENCE,
            "",
            "## Usage",
            "",
            "Call it.",
            "",
            "## Configuration",
            "",
            configuration,
            "",
            "## Dependencies",
            "",
            "Go.",
            "",
        ]
    )


BUILD = frozenset({("go", "build")})
TEST = frozenset({("go", "test")})


def judge(tmp_path: Path, old: str | None, new: str | None) -> GateResult:
    if new is not None:
        (tmp_path / "README.md").write_text(new, encoding="utf-8")
    check = ReadmeCheck(tmp_path, old, BUILD, TEST)
    return asyncio.run(check.evaluate(GateInput(tmp_path, "c" * 40, "t1", "t1-d", "t1-da1")))


def said(result: GateResult) -> list[str]:
    assert isinstance(result, Rejected)
    return [f.message for f in result.findings]


def test_a_readme_that_was_fine_and_stays_so_is_approved(tmp_path: Path) -> None:
    assert isinstance(judge(tmp_path, readme(), readme()), Approved)


def test_the_divergent_build_command_is_fixed_and_only_that_section_changes(tmp_path: Path) -> None:
    old = readme(build="make build")
    assert isinstance(judge(tmp_path, old, readme()), Approved)


def test_a_section_that_was_fine_and_changed_is_named(tmp_path: Path) -> None:
    old = readme(build="make build")
    new = readme(configuration="Environment variables.")
    assert said(judge(tmp_path, old, new)) == [
        "the README section 'Configuration' had no problem and changed"
    ]


def test_a_problem_the_documenter_left_is_reported(tmp_path: Path) -> None:
    old = readme(build="make build")
    assert said(judge(tmp_path, old, old)) == [
        "README: the build section cites make build; the project runs go build"
    ]


def test_a_readme_that_is_still_missing_is_reported(tmp_path: Path) -> None:
    assert said(judge(tmp_path, None, None)) == ["README: there is no README"]


def test_a_readme_the_documenter_created_is_judged_as_it_is(tmp_path: Path) -> None:
    assert isinstance(judge(tmp_path, None, readme()), Approved)


def test_the_readme_is_the_one_at_the_root_and_an_unreadable_one_is_none(tmp_path: Path) -> None:
    assert readme_path(tmp_path) is None
    (tmp_path / "README.md").write_bytes(b"\xff\xfe\x00\x80")
    assert readme_path(tmp_path) == "README.md"
    assert read_readme(tmp_path) == (None, None)
