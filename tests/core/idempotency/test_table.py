import pytest

from forja.core.idempotency import OPERATIONS, OperationName
from tests.core.idempotency import test_reconcilers

# Transcribed by hand from the "safe to repeat?" column of the spec table.
REPEAT_SAFE = {
    "create_task_branch": True,
    "create_attempt_worktree": True,
    "prepare_workcopy": True,
    "call_agent_cli": False,
    "apply_diff": True,
    "run_tool": True,
    "commit_stage": False,
    "integrate_task": False,
    "remove_worktree": True,
    "push_run_branch": True,
}


def test_table_has_exactly_the_operations_of_the_spec() -> None:
    assert {name.value for name in OperationName} == set(REPEAT_SAFE)
    assert set(OPERATIONS) == set(OperationName)


@pytest.mark.parametrize("name", list(OperationName))
def test_repeat_safety_matches_the_spec(name: OperationName) -> None:
    assert OPERATIONS[name].repeat_safe is REPEAT_SAFE[name.value]


@pytest.mark.parametrize("name", list(OperationName))
def test_every_rule_documents_identifier_and_reconciliation(name: OperationName) -> None:
    rule = OPERATIONS[name]
    assert rule.name is name
    assert rule.identifier
    assert rule.reconciliation
    assert bool(rule.verification) is (name is not OperationName.CALL_AGENT_CLI)


@pytest.mark.parametrize("name", list(OperationName))
def test_every_operation_has_reconciliation_tests(name: OperationName) -> None:
    tests = [n for n in dir(test_reconcilers) if n.startswith(f"test_{name.value}_")]
    assert len(tests) >= 2 or name is OperationName.CALL_AGENT_CLI
    assert tests
