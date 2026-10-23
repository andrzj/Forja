"""The test-data check: personal data an attempt adds to tests and fixtures is rejected."""

import asyncio
from pathlib import Path

from forja.checks.changes import Change, ChangeKind, Changes
from forja.checks.personal_data import PersonalDataCheck, personal_data_in
from forja.core.gates import Approved, GateInput, GateResult, Inconclusive
from forja.core.gates.models import Rejected

CPF = "529.982.247-25"
PHONE = "(11) 91234-5678"
EMAIL = "maria.silva@gmail.com"
PATH = "tests/data.txt"


def judge(
    tmp_path: Path,
    now_text: str | None,
    before: str | None = "",
    *,
    path: str = PATH,
    is_test: bool = True,
    old_path: str | None = None,
) -> GateResult:
    if now_text is not None:
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / path).write_text(now_text, encoding="utf-8")
    if now_text is None:
        kind = ChangeKind.DELETED
    elif before is None:
        kind = ChangeKind.ADDED
    elif old_path:
        kind = ChangeKind.RENAMED
    else:
        kind = ChangeKind.MODIFIED
    changes = Changes((Change(kind, path, old_path),), 0, ())
    was = {} if before is None else {old_path or path: before}
    check = PersonalDataCheck(tmp_path, changes, was, lambda p: is_test)
    return asyncio.run(check.evaluate(GateInput(tmp_path, "c" * 40, "t", "s", "a")))


def test_a_valid_cpf_added_to_a_test_file_is_rejected(tmp_path: Path) -> None:
    result = judge(tmp_path, f"cpf = '{CPF}'\n", before=None)
    assert isinstance(result, Rejected)
    assert [f.target for f in result.findings] == [PATH]
    assert "cpf" in result.findings[0].message


def test_the_finding_never_carries_the_value(tmp_path: Path) -> None:
    result = judge(tmp_path, f"{CPF} {PHONE} {EMAIL}\n", before=None)
    assert isinstance(result, Rejected)
    said = " ".join(f.message + f.target for f in result.findings)
    assert not any(v in said for v in (CPF, "91234", "maria.silva"))
    assert len(result.findings) == 3


def test_a_cpf_with_a_wrong_check_digit_is_ignored(tmp_path: Path) -> None:
    assert isinstance(judge(tmp_path, "cpf = '529.982.247-26'\n", before=None), Approved)


def test_reserved_domains_are_ignored(tmp_path: Path) -> None:
    text = "a@example.com b@host.test c@x.invalid\n"
    assert isinstance(judge(tmp_path, text, before=None), Approved)


def test_data_that_was_already_there_is_not_new(tmp_path: Path) -> None:
    text = f"cpf = '{CPF}'\nother = 1\n"
    assert isinstance(judge(tmp_path, text, before=f"cpf = '{CPF}'\n"), Approved)


def test_one_more_of_the_same_kind_is_new(tmp_path: Path) -> None:
    result = judge(tmp_path, f"{EMAIL}\nzeca@gmail.com\n", before=f"{EMAIL}\n")
    assert isinstance(result, Rejected)
    assert result.findings[0].measured == 2
    assert result.findings[0].limit == 1


def test_a_renamed_file_is_compared_with_its_old_name(tmp_path: Path) -> None:
    result = judge(tmp_path, f"{CPF}\n", before=f"{CPF}\n", path="tests/new.txt", old_path=PATH)
    assert isinstance(result, Approved)


def test_a_file_that_is_not_a_test_is_left_alone(tmp_path: Path) -> None:
    assert isinstance(judge(tmp_path, f"{CPF}\n", before=None, is_test=False), Approved)


def test_a_deleted_file_is_left_alone(tmp_path: Path) -> None:
    assert isinstance(judge(tmp_path, None, before=f"{CPF}\n"), Approved)


def test_a_file_that_cannot_be_read_is_inconclusive(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / PATH).mkdir()  # reading a directory fails
    changes = Changes((Change(ChangeKind.ADDED, PATH),), 0, ())
    check = PersonalDataCheck(tmp_path, changes, {}, lambda p: True)
    result = asyncio.run(check.evaluate(GateInput(tmp_path, "c" * 40, "t", "s", "a")))
    assert isinstance(result, Inconclusive)


def test_a_rejection_wins_over_an_unreadable_file(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "bad.txt").mkdir()
    (tmp_path / PATH).write_text(CPF, encoding="utf-8")
    changes = Changes(
        (Change(ChangeKind.ADDED, "tests/bad.txt"), Change(ChangeKind.ADDED, PATH)), 0, ()
    )
    check = PersonalDataCheck(tmp_path, changes, {}, lambda p: True)
    result = asyncio.run(check.evaluate(GateInput(tmp_path, "c" * 40, "t", "s", "a")))
    assert isinstance(result, Rejected)


def test_overlapping_patterns_count_a_place_once() -> None:
    counts = personal_data_in("+55 11 91234-5678")
    assert counts["phone"] == 1


def test_a_place_at_the_very_start_of_the_text_counts() -> None:
    assert personal_data_in(CPF)["cpf"] == 1


def test_the_message_counts_only_what_is_new(tmp_path: Path) -> None:
    result = judge(tmp_path, f"{EMAIL}\nzeca@gmail.com\nana@gmail.com\n", before=f"{EMAIL}\n")
    assert isinstance(result, Rejected)
    assert result.findings[0].message == "2 new email value(s) in test data"
