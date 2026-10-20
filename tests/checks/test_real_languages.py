"""A repair run end to end in each language, with the real tools: only the agents are scripted.

The test author adds a test that fails on the defect, the implementer fixes the production code,
and the pipeline in between is the real one (format, lint, build, tests, freeze, mutation). A
language whose tool chain is not installed is skipped.
"""

import os
import shutil
import subprocess
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

import pytest

from forja.core.adapters import LanguageAdapter
from forja.core.artifacts.llm_output import DeclaredTest
from forja.core.artifacts.models import Producer
from forja.core.events import EventLog
from forja.core.states import AttemptState, ExecutionState, Level, StageState, TaskState
from forja.languages.csharp import CSharpAdapter
from forja.languages.csharp.adapter import DOTNET_ENVIRONMENT
from forja.languages.go import GoAdapter
from forja.languages.go.adapter import GO_ENVIRONMENT, find_golangci_lint
from forja.languages.java import JavaAdapter
from forja.languages.java.adapter import JAVA_ENVIRONMENT
from forja.orchestrator.config import ExecutorRef, FixRequest, Objective
from forja.orchestrator.measurer import PipelineMeasurer
from forja.orchestrator.ports import PlannedTask
from tests.checks.support import (
    BLOCKING,
    FAKE_GITLEAKS,
    LIZARD,
    OBSERVATION,
    PREMISE,
    registry_of,
)
from tests.languages.csharp.test_mutation import LIBRARY, SOLUTION
from tests.languages.csharp.test_mutation import TESTS as CS_TESTS_PROJECT
from tests.languages.java.test_mutation import POM
from tests.orchestrator.fakes import ScriptedAgent, ScriptedPlanner
from tests.orchestrator.harness import IDENTITY, World, minimal_env

pytestmark = pytest.mark.slow

FIX = FixRequest.model_validate(
    {
        "description": "add returns the difference",
        "criteria": {
            "criteria": [{"id": 1, "text": "add sums its operands", "level": "unit", "origin": "x"}]
        },
    }
)


@dataclass(frozen=True)
class Project:
    """A small project with one defect, the test that shows it and the change that fixes it."""

    language: str
    tools: tuple[str, ...]
    base: Mapping[str, str]
    tests: Mapping[str, str]  # what the test author writes
    declared: DeclaredTest
    fix: Mapping[str, str]  # what the implementer writes
    scope: tuple[str, ...]
    env: frozenset[str]
    adapter: Callable[[Path], LanguageAdapter]


GO = Project(
    language="go",
    tools=("go",),
    base={
        "go.mod": "module example.com/calc\n\ngo 1.22\n",
        "calc.go": "package calc\n\nfunc Add(a, b int) int {\n\treturn a - b\n}\n",
        "calc_test.go": (
            'package calc\n\nimport "testing"\n\n'
            'func TestZero(t *testing.T) {\n\tif Add(0, 0) != 0 {\n\t\tt.Fatal("zero")\n\t}\n}\n'
        ),
    },
    tests={
        "calc_add_test.go": (
            'package calc\n\nimport "testing"\n\n'
            'func TestAdd(t *testing.T) {\n\tif Add(2, 3) != 5 {\n\t\tt.Fatal("add")\n\t}\n}\n'
        )
    },
    declared=DeclaredTest(
        criterion_id=1, test_id="example.com/calc/TestAdd", path="calc_add_test.go"
    ),
    fix={"calc.go": "package calc\n\nfunc Add(a, b int) int {\n\treturn a + b\n}\n"},
    scope=("calc.go",),
    env=frozenset(GO_ENVIRONMENT | {"TEMP", "TMP", "USERPROFILE"}),
    adapter=lambda root: GoAdapter(golangci_lint=find_golangci_lint()),
)

CALC_CS = (
    "namespace Calc;\n\npublic static class Calculator\n{\n"
    "    public static int Add(int a, int b)\n    {\n        return a - b;\n    }\n}\n"
)
CS_TEST = (
    "using Calc;\n\nnamespace Calc.Tests;\n\npublic class {name}\n{{\n"
    "    [Fact]\n    public void {method}()\n    {{\n"
    "        Assert.Equal({want}, Calculator.Add({a}, {b}));\n    }}\n}}\n"
)
CSHARP = Project(
    language="csharp",
    tools=("dotnet",),
    base={
        "Calc.sln": SOLUTION,
        ".gitignore": "bin/\nobj/\n.forja-coverage/\n",
        "src/Calc/Calc.csproj": LIBRARY,
        "src/Calc/Calc.cs": CALC_CS,
        "tests/Calc.Tests/Calc.Tests.csproj": CS_TESTS_PROJECT,
        "tests/Calc.Tests/ZeroTests.cs": CS_TEST.format(
            name="ZeroTests", method="Zero", want=0, a=0, b=0
        ),
    },
    tests={
        "tests/Calc.Tests/AddTests.cs": CS_TEST.format(
            name="AddTests", method="Adds", want=5, a=2, b=3
        )
    },
    declared=DeclaredTest(
        criterion_id=1, test_id="Calc.Tests.AddTests.Adds", path="tests/Calc.Tests/AddTests.cs"
    ),
    fix={"src/Calc/Calc.cs": CALC_CS.replace("a - b", "a + b")},
    scope=("src/Calc/Calc.cs",),
    env=frozenset(
        {n.upper() for n in DOTNET_ENVIRONMENT} | {"TEMP", "TMP", "SYSTEMROOT", "PATHEXT"}
    ),
    adapter=lambda root: CSharpAdapter(),
)
JAVA_CALC = (
    "package com.acme;\n\npublic final class Calc {\n  private Calc() {}\n\n"
    "  public static int add(int a, int b) {\n    return a - b;\n  }\n}\n"
)
JAVA_TEST = (
    "package com.acme;\n\nimport static org.junit.jupiter.api.Assertions.assertEquals;\n\n"
    "import org.junit.jupiter.api.Test;\n\nclass {name} {{\n"
    "  @Test\n  void {method}() {{\n    assertEquals({want}, Calc.add({a}, {b}));\n  }}\n}}\n"
)
JAVA = Project(
    language="java",
    tools=("mvn", "java"),
    base={
        "pom.xml": POM,
        ".gitignore": "target/\n",
        "src/main/java/com/acme/Calc.java": JAVA_CALC,
        "src/test/java/com/acme/ZeroTest.java": JAVA_TEST.format(
            name="ZeroTest", method="zero", want=0, a=0, b=0
        ),
    },
    tests={
        "src/test/java/com/acme/AddTest.java": JAVA_TEST.format(
            name="AddTest", method="adds", want=5, a=2, b=3
        )
    },
    declared=DeclaredTest(
        criterion_id=1, test_id="com.acme.AddTest.adds", path="src/test/java/com/acme/AddTest.java"
    ),
    fix={"src/main/java/com/acme/Calc.java": JAVA_CALC.replace("a - b", "a + b")},
    scope=("src/main/java/com/acme/Calc.java",),
    env=frozenset({n.upper() for n in JAVA_ENVIRONMENT} | {"TEMP", "TMP", "SYSTEMROOT", "PATHEXT"}),
    adapter=lambda root: JavaAdapter(),
)
PROJECTS = [GO, CSHARP, JAVA]


def host_env(project: Project, base: Mapping[str, str]) -> dict[str, str]:
    """What a real run inherits besides the minimal environment."""
    return {**base, **{k: v for k, v in os.environ.items() if k.upper() in project.env}}


def commit(path: Path, files: Mapping[str, str], env: Mapping[str, str]) -> None:
    for relative, text in files.items():
        target = path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8", newline="\n")
    git = [
        "git",
        "-c",
        f"user.name={IDENTITY.committer_name}",
        "-c",
        f"user.email={IDENTITY.committer_email}",
    ]
    for args in (
        ["init", "-b", "main"],
        ["config", "core.autocrlf", "false"],
        ["add", "-A"],
        ["commit", "-m", "base"],
    ):
        subprocess.run([*git, *args], cwd=path, env=dict(env), check=True, capture_output=True)


def world_of(project: Project, tmp_path: Path) -> World:
    (tmp_path / "home").mkdir()
    repo = tmp_path / "repo"
    repo.mkdir()
    commit(repo, project.base, minimal_env(tmp_path / "home"))
    found = World.at(tmp_path)
    found.config = found.config.model_copy(
        update={
            "objective": Objective.FIX,
            "fix": FIX,
            "test_author": ExecutorRef(name="author-cli", path="/bin/author", version="2.0"),
        }
    )
    return found


def repair(project: Project, tmp_path: Path, *fixes: Mapping[str, str]):  # type: ignore[no-untyped-def]
    world = world_of(project, tmp_path)
    log = world.open()
    settings = {
        n: BLOCKING
        for n in ("scope", "secrets", "format", "lint", "build", "tests", "red_green", "freeze")
    }
    measurer = PipelineMeasurer(
        adapters=registry_of(project.adapter(tmp_path)),
        git=world.repo.git,
        log=log,
        workdir=world.run_dir / "measure",
        host_env=host_env(project, world.repo.env),
        settings=settings
        | {
            "complexity": PREMISE,
            "mutation": OBSERVATION,
            "crap": OBSERVATION,
            "pass_through": OBSERVATION,
            "module_depth": OBSERVATION,
        },
        lizard=LIZARD,
        gitleaks=(sys.executable, str(FAKE_GITLEAKS)),
    )
    task = PlannedTask(
        "add returns the difference",
        project.scope,
        8,
        400,
        stages=(Producer.TEST_AUTHOR, Producer.IMPLEMENTER),
    )
    author = ScriptedAgent(edits=[project.tests], tests=(project.declared,))
    implementer = ScriptedAgent(edits=list(fixes) or [project.fix])
    outcome, log = world.run(
        log=log,
        measurer=measurer,
        agent=implementer,
        agents={Producer.TEST_AUTHOR: author},
        planner=ScriptedPlanner((task,)),
        extra={"test_files": measurer.test_files, "test_root": ""},
    )
    return world, outcome, log


def why(log: EventLog) -> str:
    """The reasons attempts were rejected, for a failure to explain itself."""
    return "; ".join(
        f"{attempt} {log.state.state_of(Level.ATTEMPT, attempt)}: "
        f"{log.state.transition_payload(Level.ATTEMPT, attempt, AttemptState.REJECTED)}"
        for stage in ("t1-t", "t1-s")
        for attempt in log.state.children_of(Level.ATTEMPT, stage)
    )


@pytest.mark.parametrize("project", PROJECTS, ids=lambda p: p.language)
def test_a_repair_goes_through_every_gate_and_is_delivered(
    project: Project, tmp_path: Path
) -> None:
    if any(shutil.which(tool) is None for tool in project.tools):
        pytest.skip(f"{project.language}: the tool chain is not installed")

    world, outcome, log = repair(project, tmp_path)

    assert outcome.state is ExecutionState.DELIVERED, log.state
    assert log.state.state_of(Level.TASK, "t1") is TaskState.INTEGRATED, why(log)
    assert log.state.state_of(Level.STAGE, "t1-t") is StageState.COMMITTED
    for relative in (*project.tests, *project.fix):
        assert world.repo.sh("show", f"{world.workspace.run_branch}:{relative}")


@pytest.mark.parametrize("project", PROJECTS, ids=lambda p: p.language)
def test_an_implementer_that_touches_the_frozen_tests_is_sent_back(
    project: Project, tmp_path: Path
) -> None:
    if any(shutil.which(tool) is None for tool in project.tools):
        pytest.skip(f"{project.language}: the tool chain is not installed")
    path, text = next(iter(project.tests.items()))
    tampered = {**project.fix, path: text + "\n"}

    _, outcome, log = repair(project, tmp_path, tampered, project.fix)

    assert outcome.state is ExecutionState.DELIVERED, log.state
    rejected = log.state.transition_payload(Level.ATTEMPT, "t1-a1", AttemptState.REJECTED)
    assert rejected is not None and "only production files may change" in str(rejected["reason"])
    assert log.state.state_of(Level.ATTEMPT, "t1-a2") is AttemptState.COMMITTED
