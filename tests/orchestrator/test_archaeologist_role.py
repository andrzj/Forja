"""The archaeologist: what its package says, and what answer is accepted as findings."""

from pathlib import Path

import pytest

from forja.core.artifacts.llm_output import Claim, FileCitation, LlmOutput
from forja.core.artifacts.models import Assumption, Producer
from forja.core.redaction import Redactor
from forja.orchestrator.agent_runner import _check_findings, build_package
from forja.orchestrator.config import ExecutorRef, Objective, RunConfig
from forja.orchestrator.ports import AttemptContext, RejectedWork, TaskInfo

QUESTION = "how does the page size reach the query?"
CLAIM = Claim(
    statement="it is read",
    citations=(FileCitation(kind="file", path="src/a.py", line_start=1, line_end=2),),
)
GUESS = Assumption(statement="g", reason="r", missing_evidence="m")


def package(tmp_path: Path, role: Producer, findings: str = "") -> str:
    (tmp_path / "src").mkdir(exist_ok=True)
    (tmp_path / "src" / "a.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    stage = "t1-f" if role is Producer.ARCHAEOLOGIST else "t1-d"
    task = TaskInfo("t1", stage, QUESTION, ("src/a.py",), 3, 120, role)
    ctx = AttemptContext(task, "t1-fa1", tmp_path, None, findings=findings)
    return build_package(ctx, Redactor())


def test_the_package_asks_for_claims_with_citations_and_premises_apart(tmp_path: Path) -> None:
    text = package(tmp_path, Producer.ARCHAEOLOGIST)

    assert "You are finding out how the code works" in text
    assert QUESTION in text
    assert '"claims"' in text
    assert '"assumptions"' in text
    assert '"actions": []' in text
    assert "is not a claim: put it in `assumptions`" in text
    assert "No file." in text
    assert "You cannot run commands" in text
    assert "### `src/a.py`" in text
    assert "## Findings" not in text


def test_the_documenter_of_an_investigation_gets_the_findings_to_write_from(
    tmp_path: Path,
) -> None:
    text = package(tmp_path, Producer.DOCUMENTER, "### Proven\n\n- it is read (src/a.py:1-2)")

    assert "## Findings" in text
    assert "There is no change to document in this task" in text
    assert "which you present as unverified" in text
    assert "- it is read (src/a.py:1-2)" in text


def test_a_documenter_without_findings_gets_no_such_section(tmp_path: Path) -> None:
    assert "## Findings" not in package(tmp_path, Producer.DOCUMENTER)


def test_the_findings_are_redacted_like_any_text_from_the_repository(tmp_path: Path) -> None:
    secret = "ghp_" + "A1b2C3d4" * 5
    text = package(tmp_path, Producer.DOCUMENTER, f"### Proven\n\n- the key is {secret}")

    assert secret not in text


def test_an_answer_with_a_claim_or_with_an_assumption_is_accepted() -> None:
    _check_findings(LlmOutput(claims=(CLAIM,)))
    _check_findings(LlmOutput(assumptions=(GUESS,)))


def test_an_answer_that_found_nothing_is_refused() -> None:
    with pytest.raises(RejectedWork, match="nothing was found"):
        _check_findings(LlmOutput())


def test_the_question_goes_with_the_investigate_objective_and_only_with_it() -> None:
    executor = ExecutorRef(name="c", path="/bin/c", version="1")
    common = {"repo": "r", "base_commit": "b", "implementer": executor, "forja_version": "0"}
    kept = {"policy_version": "p"}

    RunConfig(objective=Objective.INVESTIGATE, question=QUESTION, **common, **kept)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="a question is required"):
        RunConfig(objective=Objective.INVESTIGATE, **common, **kept)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="a question is required"):
        RunConfig(objective=Objective.REFACTOR, question=QUESTION, **common, **kept)  # type: ignore[arg-type]
