"""Mutation of Java code, for real: ``mvn test`` runs on copies changed by the mutator's rules.

Needs a JDK and Maven (and, the first time, the network for their plugins); the tests are skipped
without them.
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
from forja.languages.java import JavaAdapter
from forja.languages.java.adapter import JAVA_ENVIRONMENT
from tests.checks.support import RUN, sinks
from tests.core.events.support import FakeClock
from tests.core.idempotency.conftest import Repo

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(
        shutil.which("mvn") is None or shutil.which("java") is None,
        reason="a JDK and Maven are not installed",
    ),
]

POM = """<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0">
  <modelVersion>4.0.0</modelVersion>
  <groupId>com.acme</groupId>
  <artifactId>calc</artifactId>
  <version>1.0</version>
  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.junit.jupiter</groupId>
      <artifactId>junit-jupiter</artifactId>
      <version>5.11.4</version>
      <scope>test</scope>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <artifactId>maven-surefire-plugin</artifactId>
        <version>3.5.2</version>
      </plugin>
    </plugins>
  </build>
</project>
"""
CALC = (
    "package com.acme;\n\npublic final class Calc {\n  private Calc() {}\n\n"
    "  public static int add(int a, int b) {\n    return a + b;\n  }\n}\n"
)
WITH_SUB = CALC.replace(
    "  }\n}\n", "  }\n\n  public static int sub(int a, int b) {\n    return a - b;\n  }\n}\n"
)
TEST_ADD = (
    "package com.acme;\n\nimport static org.junit.jupiter.api.Assertions.assertEquals;\n\n"
    "import org.junit.jupiter.api.Test;\n\nclass CalcTest {\n"
    "  @Test\n  void adds() {\n    assertEquals(5, Calc.add(2, 3));\n  }\n"
)
TEST_THAT_CHECKS = (
    TEST_ADD + "\n  @Test\n  void subtracts() {\n    assertEquals(2, Calc.sub(3, 1));\n  }\n}\n"
)
TEST_THAT_ONLY_CALLS = TEST_ADD + "\n  @Test\n  void subtracts() {\n    Calc.sub(3, 1);\n  }\n}\n"
TEST_THAT_IS_EMPTY = TEST_ADD + "\n  @Test\n  void subtracts() {}\n}\n"
BASE = {
    "pom.xml": POM,
    ".gitignore": "target/\n",
    "src/main/java/com/acme/Calc.java": CALC,
    "src/test/java/com/acme/CalcTest.java": TEST_ADD + "}\n",
}
PRODUCTION = "src/main/java/com/acme/Calc.java"
TESTS = "src/test/java/com/acme/CalcTest.java"


def write(root: Path, name: str, text: str) -> None:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def judge(repo: Repo, tmp_path: Path, test_text: str) -> GateResult:
    """Commit the base project, then add ``sub`` with the given test file and judge the change."""
    for name, text in BASE.items():
        write(repo.path, name, text)
    repo.sh("add", "-A")
    repo.sh("commit", "-m", "project")
    write(repo.path, PRODUCTION, WITH_SUB)
    write(repo.path, TESTS, test_text)

    log = EventLog.open(tmp_path / "events.jsonl", RUN, clock=FakeClock())
    log.append_transition(Level.EXECUTION, RUN, None, ExecutionState.PREPARING)
    wanted = {name.upper() for name in JAVA_ENVIRONMENT} | {"TEMP", "TMP", "SYSTEMROOT", "PATHEXT"}
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
        tools, JavaAdapter(), repo.path, changes, (PRODUCTION,), host_env, language="java"
    )
    data = GateInput(Path("."), "c" * 40, "t", "s", "a", values={})
    return asyncio.run(check.evaluate(data))


def test_a_new_method_the_tests_check_is_approved(repo: Repo, tmp_path: Path) -> None:
    assert isinstance(judge(repo, tmp_path, TEST_THAT_CHECKS), Approved)


@pytest.mark.parametrize("test_text", [TEST_THAT_ONLY_CALLS, TEST_THAT_IS_EMPTY])
def test_a_test_that_checks_nothing_is_rejected(repo: Repo, tmp_path: Path, test_text: str) -> None:
    result = judge(repo, tmp_path, test_text)

    assert isinstance(result, Rejected)
    if test_text is TEST_THAT_ONLY_CALLS:  # the line runs, and no change to it is noticed
        assert result.findings[0].measured == 0.0
        assert any(f.target == f"{PRODUCTION}:11" for f in result.findings)
    else:  # no test runs the new line at all
        assert f"{PRODUCTION}:11" in {f.target for f in result.findings}
        assert "no test runs this new line" in result.findings[0].message
