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

# Hand-written from the spec: what each level imposes, what it only detects, what it leaves open.
SPEC = {
    "wsl": {
        "read_restricted_to_workcopy": "enforced",
        "network_allowlist": "enforced",
        "no_git_available": "enforced",
        "no_secrets": "enforced",
        "no_dot_git_in_copy": "enforced",
        "sensitive_files_absent": "enforced",
        "filtered_environment": "enforced",
        "process_tree_contained": "enforced",
    },
    "reduced": {
        "read_restricted_to_workcopy": "detected_only",
        "network_allowlist": "detected_only",
        "no_git_available": "detected_only",
        "no_secrets": "not_enforced",
        "no_dot_git_in_copy": "enforced",
        "sensitive_files_absent": "enforced",
        "filtered_environment": "enforced",
        "process_tree_contained": "enforced",
    },
}


@pytest.mark.parametrize("level", list(IsolationLevel))
def test_each_level_guarantees_exactly_what_the_spec_says(level: IsolationLevel) -> None:
    actual = {g.value: status_of(level, g).value for g in Guarantee}

    assert actual == SPEC[level.value]


def test_the_table_covers_every_guarantee_with_no_overlap() -> None:
    for level in IsolationLevel:
        assert not ENFORCED[level] & DETECTED_ONLY[level]
    assert {g.value for g in Guarantee} == set(SPEC["wsl"])


def test_the_reduced_level_never_claims_prevention_it_does_not_have() -> None:
    reduced = IsolationRecord(agent=IsolationLevel.REDUCED, repo_code=IsolationLevel.REDUCED)

    declaration = reduced.declaration()

    for context in Context:
        assert declaration[context][Guarantee.READ_RESTRICTED_TO_WORKCOPY] is Status.DETECTED_ONLY
        assert declaration[context][Guarantee.NO_SECRETS] is Status.NOT_ENFORCED


def test_the_two_contexts_can_differ_and_the_declaration_says_so() -> None:
    record = IsolationRecord(
        agent=IsolationLevel.WSL,
        repo_code=IsolationLevel.REDUCED,
        notes=("the project only builds on Windows",),
    )

    declaration = record.declaration()
    assert record.is_reduced
    assert declaration[Context.AGENT][Guarantee.NETWORK_ALLOWLIST] is Status.ENFORCED
    assert declaration[Context.REPO_CODE][Guarantee.NETWORK_ALLOWLIST] is Status.DETECTED_ONLY
    assert record.level_of(Context.REPO_CODE) is IsolationLevel.REDUCED


def test_a_fully_wsl_run_is_not_reduced() -> None:
    assert not IsolationRecord(agent=IsolationLevel.WSL, repo_code=IsolationLevel.WSL).is_reduced


def test_the_record_round_trips_through_json_and_rejects_unknown_input() -> None:
    record = IsolationRecord(
        agent=IsolationLevel.WSL, repo_code=IsolationLevel.REDUCED, notes=("x",)
    )

    assert IsolationRecord.model_validate_json(record.model_dump_json()) == record
    with pytest.raises(ValidationError):
        IsolationRecord.model_validate({"agent": "docker", "repo_code": "wsl"})
    with pytest.raises(ValidationError, match="Extra inputs"):
        IsolationRecord.model_validate({"agent": "wsl", "repo_code": "wsl", "extra": 1})
