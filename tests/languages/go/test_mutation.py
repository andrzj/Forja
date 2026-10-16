"""Mutation of Go code, for real: ``go test`` runs on copies changed by the mutator's rules.

Needs the Go tool chain; the tests are skipped without it.
"""

import asyncio
import os
import shutil
from pathlib import Path

import pytest

from forja.checks.changes import read_changes
from forja.checks.mutation import MutationCheck
from forja.checks.tooling import Tools
from forja.core.events import EventLog
from forja.core.gates import GateInput
from forja.core.gates.models import Approved, GateResult, Rejected
from forja.core.states import ExecutionState, Level
from forja.languages.go import GoAdapter
from forja.languages.go.adapter import GO_ENVIRONMENT
from tests.checks.support import RUN, sinks
from tests.core.events.support import FakeClock
from tests.core.idempotency.conftest import Repo

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(shutil.which("go") is None, reason="the Go tool chain is not installed"),
]

BASE = {
    "go.mod": "module example.com/calc\n\ngo 1.22\n",
    "calc.go": "package calc\n\nfunc Add(a, b int) int {\n\treturn a + b\n}\n",
    "calc_test.go": (
        'package calc\n\nimport "testing"\n\n'
        "func TestAdd(t *testing.T) {\n"
        '\tif Add(2, 3) != 5 {\n\t\tt.Fatal("add")\n\t}\n}\n'
    ),
}
WITH_SUB = BASE["calc.go"] + "\nfunc Sub(a, b int) int {\n\treturn a - b\n}\n"
TEST_ADD = BASE["calc_test.go"]
TEST_THAT_CHECKS = TEST_ADD + (
    '\nfunc TestSub(t *testing.T) {\n\tif Sub(3, 1) != 2 {\n\t\tt.Fatal("sub")\n\t}\n}\n'
)
TEST_THAT_ONLY_CALLS = TEST_ADD + "\nfunc TestSub(t *testing.T) {\n\tSub(3, 1)\n}\n"
TEST_THAT_IS_EMPTY = TEST_ADD + "\nfunc TestSub(t *testing.T) {\n}\n"


def judge(repo: Repo, tmp_path: Path, test_text: str) -> GateResult:
    """Commit the base module, then add ``Sub`` with the given test file and judge the change."""
    for name, text in BASE.items():
        (repo.path / name).write_text(text, encoding="utf-8", newline="\n")
    repo.sh("add", "-A")
    repo.sh("commit", "-m", "module")
    (repo.path / "calc.go").write_text(WITH_SUB, encoding="utf-8", newline="\n")
    (repo.path / "calc_test.go").write_text(test_text, encoding="utf-8", newline="\n")

    log = EventLog.open(tmp_path / "events.jsonl", RUN, clock=FakeClock())
    log.append_transition(Level.EXECUTION, RUN, None, ExecutionState.PREPARING)
    wanted = GO_ENVIRONMENT | {"TEMP", "TMP", "USERPROFILE"}  # what a real run inherits
    host_env = {**repo.env, **{k: v for k, v in os.environ.items() if k.upper() in wanted}}
    tools = Tools(
        sinks=sinks,
        log=log,
        level=Level.ATTEMPT,
        target="a",
        logs=tmp_path / "tool-logs",
        host_env=host_env,
    )
    changes = asyncio.run(read_changes(repo.git.at(repo.path)))
    check = MutationCheck(
        tools,
        GoAdapter(),
        repo.path,
        changes,
        ("calc.go",),
        host_env,
        language="go",
    )
    data = GateInput(Path("."), "c" * 40, "t", "s", "a", values={})
    return asyncio.run(check.evaluate(data))


def test_a_new_function_the_tests_check_is_approved(repo: Repo, tmp_path: Path) -> None:
    assert isinstance(judge(repo, tmp_path, TEST_THAT_CHECKS), Approved)


@pytest.mark.parametrize("test_text", [TEST_THAT_ONLY_CALLS, TEST_THAT_IS_EMPTY])
def test_a_test_that_checks_nothing_is_rejected(repo: Repo, tmp_path: Path, test_text: str) -> None:
    result = judge(repo, tmp_path, test_text)

    assert isinstance(result, Rejected)
    if test_text is TEST_THAT_ONLY_CALLS:  # the line runs, and no change to it is noticed
        assert result.findings[0].measured == 0.0
        assert result.findings[0].limit == 0.70
        assert any(f.target == "calc.go:8" for f in result.findings)
    else:  # no test runs the new line at all
        # the body and the closing brace the profile counts in the same block
        assert {f.target for f in result.findings} == {"calc.go:8", "calc.go:9"}
        assert "no test runs this new line" in result.findings[0].message
