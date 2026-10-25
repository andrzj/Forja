"""A task that brings a new dependency or module owes a decision record with the right parts."""

import asyncio
from pathlib import Path

from forja.checks.adr_trigger import (
    DEPENDENCY,
    AdrCheck,
    Trigger,
    missing_sections,
    new_modules,
    next_number,
    numbers_in,
    report,
)
from forja.core.artifacts.models import Producer
from forja.core.gates import Approved, GateInput, GateResult, Rejected
from forja.core.redaction import Redactor
from forja.orchestrator.agent_runner import build_package
from forja.orchestrator.ports import AttemptContext, TaskInfo
from tests.checks.test_readme_paths import link_or_skip

SECTIONS = ["# 0003. Use x", "## Context", "c", "## Decision", "d"]
SECTIONS += ["## Alternatives", "a", "## Consequences", "c"]
GOOD = "\n\n".join(SECTIONS) + "\n"
DEP = Trigger(DEPENDENCY, "requests", "pyproject.toml")


def judge(tmp_path: Path, triggers: tuple[Trigger, ...], before: set[str]) -> GateResult:
    check = AdrCheck(tmp_path, triggers, frozenset(before))
    return asyncio.run(check.evaluate(GateInput(tmp_path, "c" * 40, "t1", "t1-d", "t1-da1")))


def record(tmp_path: Path, name: str, text: str) -> None:
    (tmp_path / "docs" / "adr").mkdir(parents=True, exist_ok=True)
    (tmp_path / "docs" / "adr" / name).write_text(text, encoding="utf-8")


def said(result: GateResult) -> list[str]:
    assert isinstance(result, Rejected)
    return [f.message for f in result.findings]


def test_a_directory_is_a_new_module_when_it_had_no_production_file_at_the_base() -> None:
    found = new_modules(
        ["src/a/new.py", "src/b/x.py", "src/b/y.py", "top.py", "src/old/more.py"],
        ["src/old/one.py"],
        {"src/a/new.py", "src/b/x.py", "src/b/y.py", "top.py", "src/old/more.py"},
    )
    assert [(t.subject, t.where) for t in found] == [
        ("src/a", "src/a/new.py"),
        ("src/b", "src/b/x.py"),
    ]


def test_a_new_file_that_is_not_production_makes_no_module() -> None:
    assert new_modules(["tests/new/test_a.py"], [], set()) == []


def test_numbers_are_those_of_the_records_in_the_adr_folder_and_the_next_is_free() -> None:
    paths = ["docs/adr/0001-a.md", "docs/adr/0007-b.md", "docs/adr/README.md", "docs/x/0009-c.md"]
    assert numbers_in(paths) == {1, 7}
    assert next_number(paths) == 8
    assert next_number([]) == 1


def test_the_report_names_the_triggers_and_the_number_to_use() -> None:
    text = report([DEP], ["docs/adr/0002-a.md"])
    assert "new external dependency `requests` (pyproject.toml)" in text
    assert "docs/adr/0003-<short-title>.md" in text
    assert report([], []) == ""


def test_sections_are_found_in_portuguese_and_english() -> None:
    assert missing_sections(GOOD) == []
    assert missing_sections("# x\n\n## Alternativas\n\na\n\n## Consequências\n\nb\n") == []
    assert missing_sections("# x\n\n## Decision\n\nd\n") == ["alternatives", "consequences"]


def test_no_trigger_needs_no_record(tmp_path: Path) -> None:
    assert isinstance(judge(tmp_path, (), set()), Approved)


def test_a_trigger_without_a_new_record_is_rejected(tmp_path: Path) -> None:
    assert said(judge(tmp_path, (DEP,), set())) == [
        "new external dependency `requests` (pyproject.toml): the task owes a record under docs/adr"
    ]


def test_a_record_with_the_parts_answers_the_rule_and_an_extra_one_is_not_rejected(
    tmp_path: Path,
) -> None:
    record(tmp_path, "0003-use-x.md", GOOD)
    record(tmp_path, "0004-extra.md", "# nothing\n")
    assert isinstance(judge(tmp_path, (DEP,), {"docs/adr/0001-a.md"}), Approved)


def test_a_record_missing_its_alternatives_or_with_a_taken_number_is_rejected(
    tmp_path: Path,
) -> None:
    record(tmp_path, "0001-use-x.md", "# x\n\n## Consequences\n\nc\n")
    assert said(judge(tmp_path, (DEP,), {"docs/adr/0001-a.md"})) == [
        "the record has no section on the alternatives",
        "record number 1 is taken",
    ]


def test_a_record_that_was_already_there_is_not_a_new_one(tmp_path: Path) -> None:
    record(tmp_path, "0001-a.md", GOOD)
    assert isinstance(judge(tmp_path, (DEP,), {"docs/adr/0001-a.md"}), Rejected)


def test_what_a_record_is_owed_for_is_redacted_before_it_reaches_the_agent(
    tmp_path: Path,
) -> None:
    token = "ghp_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"
    task = TaskInfo("t1", "t1-d", "reduce", (), 3, 120, Producer.DOCUMENTER)
    owed = report([Trigger(DEPENDENCY, token, "pyproject.toml")], [])
    ctx = AttemptContext(task, "t1-da1", tmp_path, None, adr=owed)

    text = build_package(ctx, Redactor())

    assert token not in text
    assert "## Decision record owed" in text
    assert "docs/adr/0001-<short-title>.md" in text


def owes_a_record(result: GateResult) -> bool:
    return len(said(result)) == 1 and "owes a record" in said(result)[0]


def test_a_record_the_stage_began_with_is_not_a_new_record(tmp_path: Path) -> None:
    record(tmp_path, "0001-old.md", GOOD.replace("0003", "0001"))
    assert owes_a_record(judge(tmp_path, (DEP,), {"docs/adr/0001-old.md"}))


def test_a_file_in_the_folder_that_is_not_a_record_is_left_alone(tmp_path: Path) -> None:
    record(tmp_path, "README.md", "index\n")
    assert owes_a_record(judge(tmp_path, (DEP,), set()))


def test_a_link_in_the_folder_is_not_a_record(tmp_path: Path) -> None:
    (tmp_path / "docs" / "adr").mkdir(parents=True)
    (tmp_path / "good.md").write_text(GOOD, encoding="utf-8")
    link_or_skip(tmp_path / "docs" / "adr" / "0004-link.md", tmp_path / "good.md")
    assert owes_a_record(judge(tmp_path, (DEP,), set()))
