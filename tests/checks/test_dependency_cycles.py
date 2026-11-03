"""The dependency cycles check: a new cycle, or an old one that grew, is rejected."""

import asyncio
from pathlib import Path

import pytest

from forja.checks.architecture.compare import Snapshot
from forja.checks.dependency_cycles import DependencyCyclesCheck
from forja.checks.specs import default_registry
from forja.core.gates import GateInput, InconclusiveReason, Mode
from forja.core.gates.models import Approved, GateResult, Inconclusive, Rejected


def tree(**imports: str) -> dict[str, str]:
    """A Python project of one package per name, each importing what the text says."""
    return {f"{name}/__init__.py": text for name, text in imports.items()}


def judge(before: dict[str, str], after: dict[str, str], changed: tuple[str, ...]) -> GateResult:
    check = DependencyCyclesCheck(Snapshot("python", before), Snapshot("python", after), changed)
    data = GateInput(Path("."), "c" * 40, "t", "s", "a")
    return asyncio.run(check.evaluate(data))


def test_the_check_belongs_to_gate_9_in_observation_and_blocks_when_it_cannot_measure() -> None:
    spec = default_registry().get("dependency_cycles")

    assert spec.default_on_inconclusive is not None
    assert (spec.gate, spec.default_mode, spec.default_on_inconclusive.value) == (
        9,
        Mode.OBSERVATION,
        "block",
    )


def test_a_new_cycle_is_rejected_and_the_message_gives_the_path() -> None:
    before = tree(a="import b\n", b="")
    after = tree(a="import b\n", b="import a\n")

    result = judge(before, after, ("b/__init__.py",))

    assert isinstance(result, Rejected)
    (finding,) = result.findings
    assert finding.message == "new dependency cycle between directories"
    assert (finding.target, finding.measured) == ("b -> a -> b", 2)


def test_the_path_starts_in_a_directory_the_attempt_touched() -> None:
    before = tree(a="import b\n", b="import c\n", c="")
    after = tree(a="import b\n", b="import c\n", c="import a\n")

    result = judge(before, after, ("c/__init__.py",))

    assert isinstance(result, Rejected)
    assert result.findings[0].target == "c -> a -> b -> c"


def test_an_old_cycle_that_stays_the_same_is_the_pasts_and_passes() -> None:
    both = tree(a="import b\n", b="import a\n")
    after = {**both, "a/extra.py": "x = 1\n"}

    assert isinstance(judge(both, after, ("a/extra.py",)), Approved)


def test_an_old_cycle_that_shrinks_passes() -> None:
    before = tree(a="import b\n", b="import c\n", c="import a\n")
    after = tree(a="import b\n", b="import a\n", c="")

    assert isinstance(judge(before, after, ("b/__init__.py",)), Approved)


def test_an_old_cycle_that_takes_in_a_directory_is_rejected() -> None:
    before = tree(a="import b\n", b="import a\n", c="")
    after = tree(a="import b\n", b="import a\nimport c\n", c="import a\n")

    result = judge(before, after, ("b/__init__.py", "c/__init__.py"))

    assert isinstance(result, Rejected)
    (finding,) = result.findings
    assert finding.message == "a dependency cycle took in more directories"
    assert (finding.target.split(" -> ")[0], finding.measured) == ("c", 3)


def test_two_new_cycles_are_two_findings() -> None:
    before = tree(a="", b="", c="", d="")
    after = tree(a="import b\n", b="import a\n", c="import d\n", d="import c\n")

    result = judge(before, after, ("a/__init__.py", "c/__init__.py"))

    assert isinstance(result, Rejected)
    assert [f.target for f in result.findings] == ["a -> b -> a", "c -> d -> c"]


def test_an_attempt_that_changes_no_production_file_of_a_language_read_passes() -> None:
    cycle = tree(a="import b\n", b="import a\n")

    assert isinstance(judge({}, cycle, ()), Approved)
    assert isinstance(judge({}, cycle, ("notes.rb",)), Approved)
    assert isinstance(judge(cycle, cycle, ("gone/__init__.py",)), Approved)  # a deletion


def test_a_changed_file_that_does_not_parse_is_inconclusive() -> None:
    before = tree(a="", b="")
    after = tree(a="def (:\n", b="import a\n")

    result = judge(before, after, ("a/__init__.py",))

    assert isinstance(result, Inconclusive)
    assert result.reason is InconclusiveReason.UNSUPPORTED_CONSTRUCT
    assert "a/__init__.py" in result.detail


def test_a_file_the_attempt_did_not_change_that_does_not_parse_stays_out() -> None:
    before = tree(a="", b="")
    after = {**tree(a="import b\n", b="import a\n"), "z/__init__.py": "def (:\n"}

    result = judge(before, after, ("a/__init__.py",))

    assert isinstance(result, Rejected)


def test_a_project_with_no_file_to_read_after_the_attempt_is_inconclusive() -> None:
    result = judge({}, {"a/__init__.py": "def (:\n"}, ("a/__init__.py",))

    assert isinstance(result, Inconclusive)


def test_a_parent_commit_with_nothing_to_read_has_no_cycles_to_forgive() -> None:
    after = tree(a="import b\n", b="import a\n")

    assert isinstance(judge({}, after, ("a/__init__.py",)), Rejected)


def test_go_has_no_cycle_to_find() -> None:
    files = {"a/a.go": 'package a\nimport "ex.com/m/b"\n', "b/b.go": "package b\n"}
    mod = "module ex.com/m\n"
    check = DependencyCyclesCheck(
        Snapshot("go", files, mod), Snapshot("go", files, mod), ("a/a.go",)
    )
    data = GateInput(Path("."), "c" * 40, "t", "s", "a")

    assert isinstance(asyncio.run(check.evaluate(data)), Approved)


@pytest.mark.parametrize(
    ("language", "files"),
    [
        (
            "typescript",
            {"a/a.ts": "import '../b/b';\n", "b/b.ts": "import '../a/a';\n"},
        ),
        (
            "java",
            {
                "a/A.java": "package a;\nimport b.B;\nclass A {}",
                "b/B.java": "package b;\nimport a.A;\nclass B {}",
            },
        ),
        (
            "csharp",
            {
                "A/A.cs": "using B;\nnamespace A { class X {} }",
                "B/B.cs": "using A;\nnamespace B { class Y {} }",
            },
        ),
    ],
)
def test_a_new_cycle_is_found_in_the_other_languages(language: str, files: dict[str, str]) -> None:
    check = DependencyCyclesCheck(Snapshot(language, {}), Snapshot(language, files), tuple(files))
    data = GateInput(Path("."), "c" * 40, "t", "s", "a")

    result = asyncio.run(check.evaluate(data))

    assert isinstance(result, Rejected)


def test_the_finding_counts_the_directories_of_the_cycle_against_a_limit_of_one() -> None:
    result = judge(
        tree(a="", b="", c=""),
        tree(a="import b\n", b="import c\n", c="import a\n"),
        ("c/__init__.py",),
    )

    assert isinstance(result, Rejected)
    assert (result.findings[0].measured, result.findings[0].limit) == (3, 1)
