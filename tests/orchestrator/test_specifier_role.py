"""The specifier: what its package says, and what answer is accepted as criteria."""

from pathlib import Path

import pytest

from forja.core.artifacts.llm_output import Criterion, CriterionLevel, LlmOutput
from forja.core.artifacts.models import Producer
from forja.core.redaction import Redactor
from forja.orchestrator.agent_runner import _check_criteria, build_package
from forja.orchestrator.ports import AttemptContext, RejectedWork, TaskInfo

INTENT = "- page 1 shows the wrong items\n- the last page is empty"


def specifier_package(tmp_path: Path, intent: str = INTENT) -> str:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    task = TaskInfo("t1", "t1-c", intent, ("src/a.py",), 3, 120, Producer.SPECIFIER)
    return build_package(AttemptContext(task, "t1-ca1", tmp_path, None), Redactor())


def test_the_package_lists_the_elements_with_their_ids(tmp_path: Path) -> None:
    text = specifier_package(tmp_path)

    assert "## Elements of the input" in text
    assert "- E1: page 1 shows the wrong items" in text
    assert "- E2: the last page is empty" in text


def test_the_package_says_what_to_answer_and_that_no_file_may_change(tmp_path: Path) -> None:
    text = specifier_package(tmp_path)

    assert "You are writing the acceptance criteria" in text
    assert '"criteria"' in text
    assert '"origin": ["E1"]' in text
    assert '"left_out"' in text
    assert "No file." in text
    assert "You cannot run commands" in text
    assert "### `src/a.py`" in text


def test_the_package_of_the_other_roles_has_no_elements(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("x = 1\n", encoding="utf-8")
    for role in (Producer.IMPLEMENTER, Producer.TEST_AUTHOR, Producer.DOCUMENTER):
        task = TaskInfo("t1", "t1-s", INTENT, ("src/a.py",), 3, 120, role)
        text = build_package(AttemptContext(task, "t1-a1", tmp_path, None), Redactor())
        assert "Elements of the input" not in text
        assert "acceptance criteria for the task" not in text


def criterion(number: int) -> Criterion:
    return Criterion(id=number, text="t", level=CriterionLevel.UNIT, origin=("E1",))


def test_an_answer_with_criteria_is_accepted() -> None:
    _check_criteria(LlmOutput(criteria=(criterion(1), criterion(2))))


def test_an_answer_with_no_criteria_is_refused() -> None:
    with pytest.raises(RejectedWork, match="the criteria are not valid"):
        _check_criteria(LlmOutput())


def test_an_answer_that_numbers_two_criteria_alike_is_refused() -> None:
    with pytest.raises(RejectedWork, match="criterion ids must be unique"):
        _check_criteria(LlmOutput(criteria=(criterion(1), criterion(1))))
