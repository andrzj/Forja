from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from forja.core.artifacts import (
    ArtifactStore,
    ArtifactType,
    AuthoredTestsBody,
    ChangeRecordBody,
    CriteriaBody,
    ExecutionSummaryBody,
    Executor,
    FindingsBody,
    Producer,
    TaskDefinitionBody,
)

COMMIT = "b" * 40
CITATION = {"kind": "fact", "fact_id": "f1"}

VALID: dict[ArtifactType, tuple[type[BaseModel], dict[str, Any]]] = {
    ArtifactType.FINDINGS: (
        FindingsBody,
        {"claims": [{"statement": "parse is pure", "citations": [CITATION]}]},
    ),
    ArtifactType.CRITERIA: (
        CriteriaBody,
        {
            "criteria": [
                {"id": 1, "text": "rejects bad input", "level": "unit", "origin": "section 2"},
                {"id": 2, "text": "end to end flow", "level": "e2e", "origin": "section 3"},
            ]
        },
    ),
    ArtifactType.TEST_MANIFEST: (
        AuthoredTestsBody,
        {
            "tests": [{"criterion_id": 1, "test_id": "t_bad_input", "path": "tests/test_a.py"}],
            "generators": [{"name": "users", "seed": 7, "path": "tests/gen.py"}],
        },
    ),
    ArtifactType.CHANGE_RECORD: (
        ChangeRecordBody,
        {
            "files": [{"path": "src/a.py", "change": "modified"}],
            "symbols": [
                {"path": "src/a.py", "name": "parse", "kind": "function", "change": "modified"}
            ],
            "evidence_before": ["ev1"],
            "evidence_after": ["ev2"],
            "gates_passed": ["scope", "tests"],
            "toolchains": [{"name": "python", "version": "3.12.4"}],
            "executors": [{"cli": "claude-code", "version": "2.1.0"}],
            "revert_commit": COMMIT,
        },
    ),
    ArtifactType.EXECUTION_SUMMARY: (
        ExecutionSummaryBody,
        {
            "tasks": [
                {"task_id": "t1", "outcome": "integrated", "attempts": 3, "rejected_attempts": 2},
                {
                    "task_id": "t2",
                    "outcome": "blocked",
                    "attempts": 3,
                    "rejected_attempts": 3,
                    "duration_seconds": 12.5,
                    "tokens": 4000,
                },
            ],
            "total_duration_seconds": 100.0,
        },
    ),
    ArtifactType.TASK_DEFINITION: (
        TaskDefinitionBody,
        {
            "role": "implementer",
            "intent": "extract the parser",
            "scope": ["src/a.py", "src/b.py"],
            "max_files": 5,
            "max_lines": 200,
            "depends_on": ["t0"],
        },
    ),
}


def test_every_artifact_type_has_a_valid_example() -> None:
    assert set(VALID) == set(ArtifactType) - {ArtifactType.CHANGE_DECLARATION}


@pytest.mark.parametrize("artifact_type", list(VALID), ids=lambda t: t.value)
def test_each_body_round_trips_through_the_store(
    tmp_path: Path, artifact_type: ArtifactType
) -> None:
    model, data = VALID[artifact_type]
    store = ArtifactStore(tmp_path)
    forja_made = artifact_type in (ArtifactType.TASK_DEFINITION, ArtifactType.EXECUTION_SUMMARY)

    header = store.put(
        artifact_type=artifact_type,
        producer=Producer.FORJA if forja_made else Producer.IMPLEMENTER,
        executor=None if forja_made else Executor(cli="c", version="1"),
        body=model.model_validate(data),
    )

    assert store.get(header.id).body == model.model_validate(data)


@pytest.mark.parametrize("artifact_type", list(VALID), ids=lambda t: t.value)
def test_unknown_fields_are_rejected(artifact_type: ArtifactType) -> None:
    model, data = VALID[artifact_type]

    with pytest.raises(ValidationError, match="Extra inputs"):
        model.model_validate({**data, "surprise": 1})


def invalid(artifact_type: ArtifactType, **changes: Any) -> None:
    model, data = VALID[artifact_type]
    with pytest.raises(ValidationError):
        model.model_validate({**data, **changes})


def test_criteria_need_unique_positive_numbers_and_a_known_level() -> None:
    first = {"id": 1, "text": "a", "level": "unit", "origin": "o"}
    invalid(ArtifactType.CRITERIA, criteria=[])
    invalid(ArtifactType.CRITERIA, criteria=[first, first])
    invalid(ArtifactType.CRITERIA, criteria=[{**first, "id": 0}])
    invalid(ArtifactType.CRITERIA, criteria=[{**first, "level": "manual"}])
    invalid(ArtifactType.CRITERIA, criteria=[{**first, "origin": " "}])


def test_authored_tests_need_unique_ids_and_safe_paths() -> None:
    test = {"criterion_id": 1, "test_id": "t", "path": "tests/a.py"}
    invalid(ArtifactType.TEST_MANIFEST, tests=[])
    invalid(ArtifactType.TEST_MANIFEST, tests=[test, test])
    invalid(ArtifactType.TEST_MANIFEST, tests=[{**test, "path": "../outside.py"}])
    invalid(ArtifactType.TEST_MANIFEST, tests=[{**test, "criterion_id": 0}])
    gen = {"name": "g", "seed": 1, "path": "tests/g.py"}
    invalid(ArtifactType.TEST_MANIFEST, generators=[gen, gen])
    invalid(ArtifactType.TEST_MANIFEST, generators=[{**gen, "seed": -1}])


def test_a_change_record_must_say_how_to_revert_it() -> None:
    _, data = VALID[ArtifactType.CHANGE_RECORD]
    without = {k: v for k, v in data.items() if k != "revert_commit"}
    with pytest.raises(ValidationError, match="revert_commit"):
        ChangeRecordBody.model_validate(without)
    invalid(ArtifactType.CHANGE_RECORD, revert_commit="HEAD~1")
    invalid(ArtifactType.CHANGE_RECORD, files=[{"path": "/abs.py", "change": "created"}])


def test_summary_rejections_cannot_exceed_attempts_and_task_ids_are_unique() -> None:
    task = {"task_id": "t", "outcome": "integrated", "attempts": 1, "rejected_attempts": 1}
    ExecutionSummaryBody.model_validate({"tasks": [task]})
    invalid(ArtifactType.EXECUTION_SUMMARY, tasks=[{**task, "rejected_attempts": 2}])
    invalid(ArtifactType.EXECUTION_SUMMARY, tasks=[task, task])
    invalid(ArtifactType.EXECUTION_SUMMARY, tasks=[{**task, "outcome": "rejected"}])
    invalid(ArtifactType.EXECUTION_SUMMARY, tasks=[{**task, "duration_seconds": float("nan")}])
    invalid(ArtifactType.EXECUTION_SUMMARY, total_duration_seconds=-1)


def test_cost_fields_of_the_summary_are_optional() -> None:
    body = ExecutionSummaryBody.model_validate(
        {"tasks": [{"task_id": "t", "outcome": "cancelled", "attempts": 0, "rejected_attempts": 0}]}
    )

    assert body.tasks[0].tokens is None and body.tasks[0].duration_seconds is None
    assert body.total_duration_seconds is None


def test_a_task_definition_has_a_role_a_bounded_scope_and_unique_lists() -> None:
    invalid(ArtifactType.TASK_DEFINITION, role="forja")
    invalid(ArtifactType.TASK_DEFINITION, role="reviewer")
    invalid(ArtifactType.TASK_DEFINITION, scope=[])
    invalid(ArtifactType.TASK_DEFINITION, scope=["a.py", "a.py"])
    invalid(ArtifactType.TASK_DEFINITION, scope=["C:/x.py"])
    invalid(ArtifactType.TASK_DEFINITION, max_files=0)
    invalid(ArtifactType.TASK_DEFINITION, max_lines=0)
    invalid(ArtifactType.TASK_DEFINITION, depends_on=["t0", "t0"])
    invalid(ArtifactType.TASK_DEFINITION, intent="")
