import pytest
from pydantic import ValidationError

from forja.core.isolation import (
    DETECTED_ONLY,
    ENFORCED,
    Context,
    Guarantee,
    IsolationLevel,
    IsolationRecord,
    Status,
    status_of,
)

# Hand-written: what the Forja imposes, what it only notices, what it leaves to the environment.
SPEC = {
    "environment": {
        "read_restricted_to_workcopy": "environment",
        "network_allowlist": "environment",
        "no_git_available": "detected_only",
        "no_secrets": "environment",
        "no_dot_git_in_copy": "enforced",
        "sensitive_files_absent": "enforced",
        "filtered_environment": "enforced",
        "process_tree_contained": "enforced",
    },
}


@pytest.mark.parametrize("level", list(IsolationLevel))
def test_each_level_guarantees_exactly_what_is_written_here(level: IsolationLevel) -> None:
    actual = {g.value: status_of(level, g).value for g in Guarantee}

    assert actual == SPEC[level.value]


def test_the_table_covers_every_guarantee_with_no_overlap() -> None:
    for level in IsolationLevel:
        assert not ENFORCED[level] & DETECTED_ONLY[level]
    assert {g.value for g in Guarantee} == set(SPEC["environment"])


def test_the_forja_never_claims_what_only_the_environment_can_give() -> None:
    record = IsolationRecord(agent=IsolationLevel.ENVIRONMENT, repo_code=IsolationLevel.ENVIRONMENT)

    declaration = record.declaration()

    for context in Context:
        assert declaration[context][Guarantee.READ_RESTRICTED_TO_WORKCOPY] is Status.ENVIRONMENT
        assert declaration[context][Guarantee.NETWORK_ALLOWLIST] is Status.ENVIRONMENT
        assert declaration[context][Guarantee.NO_SECRETS] is Status.ENVIRONMENT


def test_the_record_round_trips_through_json_and_rejects_unknown_input() -> None:
    record = IsolationRecord(
        agent=IsolationLevel.ENVIRONMENT, repo_code=IsolationLevel.ENVIRONMENT, notes=("x",)
    )

    assert IsolationRecord.model_validate_json(record.model_dump_json()) == record
    with pytest.raises(ValidationError):
        IsolationRecord.model_validate({"agent": "docker", "repo_code": "environment"})
    with pytest.raises(ValidationError, match="Extra inputs"):
        IsolationRecord.model_validate(
            {"agent": "environment", "repo_code": "environment", "extra": 1}
        )
