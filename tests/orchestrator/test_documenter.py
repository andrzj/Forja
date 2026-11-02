"""The documenter is the last stage of a task; the Forja writes the record, not the agent."""

from pathlib import Path

import pytest

from forja.core.artifacts.models import Producer
from forja.core.redaction import Redactor
from forja.core.states import AttemptState, ExecutionState, Level, StageState, TaskState
from forja.orchestrator.agent_runner import redacted_diary
from forja.orchestrator.ports import PlannedTask
from tests.orchestrator.fakes import (
    PASSED,
    REJECTED,
    ScriptedAgent,
    ScriptedMeasurer,
    ScriptedPlanner,
)
from tests.orchestrator.harness import MemoryWorld

TASK = PlannedTask(
    "reduce the complexity of f",
    ("src/a.py",),
    8,
    400,
    stages=(Producer.IMPLEMENTER, Producer.DOCUMENTER),
)
CODE = {"src/a.py": "def f():\n    return 1\n"}
README = {"README.md": "# a\n\nf returns 1.\n"}


@pytest.fixture
def world(tmp_path: Path) -> MemoryWorld:
    return MemoryWorld(tmp_path)


def test_the_documenter_stage_comes_last_and_the_task_is_integrated_after_it(
    world: MemoryWorld,
) -> None:
    measurer = ScriptedMeasurer()

    outcome, log = world.run(
        measurer=measurer,
        agent=ScriptedAgent(edits=[CODE]),
        agents={Producer.DOCUMENTER: ScriptedAgent(edits=[README])},
        planner=ScriptedPlanner((TASK,)),
    )

    assert outcome.state is ExecutionState.DELIVERED
    assert log.state.state_of(Level.STAGE, "t1-s") is StageState.COMMITTED
    assert log.state.state_of(Level.STAGE, "t1-d") is StageState.COMMITTED
    assert log.state.state_of(Level.TASK, "t1") is TaskState.INTEGRATED
    assert log.state.children_of(Level.ATTEMPT, "t1-d") == ["t1-da1"]


def test_the_documenter_commit_is_a_docs_commit_with_the_record_in_it(world: MemoryWorld) -> None:
    world.run(
        measurer=ScriptedMeasurer(),
        agent=ScriptedAgent(edits=[CODE]),
        agents={Producer.DOCUMENTER: ScriptedAgent(edits=[README])},
        planner=ScriptedPlanner((TASK,)),
    )

    memory = world.memory
    tip = memory.branches[world.workspace.run_branch]
    commits = [memory.commits[sha] for sha in memory.ancestors(tip)]
    docs = [c for c in commits if c.subject.startswith("docs: ")]
    assert [c.subject for c in docs] == ["docs: reduce the complexity of f"]
    assert docs[0].tree["docs/mudancas/t1.md"] == "record of t1\n"
    assert docs[0].tree["README.md"] == README["README.md"]


def test_a_documenter_that_changes_nothing_still_leaves_the_record_to_commit(
    world: MemoryWorld,
) -> None:
    outcome, log = world.run(
        measurer=ScriptedMeasurer(),
        agent=ScriptedAgent(edits=[CODE]),
        agents={Producer.DOCUMENTER: ScriptedAgent(edits=[])},
        planner=ScriptedPlanner((TASK,)),
    )

    assert outcome.state is ExecutionState.DELIVERED
    assert log.state.state_of(Level.STAGE, "t1-d") is StageState.COMMITTED


def test_the_record_is_asked_for_with_the_gates_the_earlier_stage_passed(
    world: MemoryWorld,
) -> None:
    measurer = ScriptedMeasurer()

    world.run(
        measurer=measurer,
        agent=ScriptedAgent(edits=[CODE]),
        agents={Producer.DOCUMENTER: ScriptedAgent(edits=[README])},
        planner=ScriptedPlanner((TASK,)),
    )

    assert measurer.recorded == [("t1", ["complexity"])]


def test_a_documenter_rejected_by_a_gate_is_tried_again_without_touching_the_code_stage(
    world: MemoryWorld,
) -> None:
    measurer = ScriptedMeasurer(verdicts=(PASSED, REJECTED, PASSED))

    outcome, log = world.run(
        measurer=measurer,
        agent=ScriptedAgent(edits=[CODE]),
        agents={Producer.DOCUMENTER: ScriptedAgent(edits=[README])},
        planner=ScriptedPlanner((TASK,)),
    )

    assert outcome.state is ExecutionState.DELIVERED
    assert log.state.children_of(Level.ATTEMPT, "t1-s") == ["t1-a1"]
    assert log.state.children_of(Level.ATTEMPT, "t1-d") == ["t1-da1", "t1-da2"]
    assert log.state.state_of(Level.ATTEMPT, "t1-da1") is AttemptState.REJECTED
    assert log.state.state_of(Level.ATTEMPT, "t1-da2") is AttemptState.COMMITTED


def test_the_log_book_of_the_task_goes_in_the_documenter_commit_beside_the_record(
    world: MemoryWorld,
) -> None:
    world.run(
        measurer=ScriptedMeasurer(verdicts=(REJECTED, PASSED, PASSED)),
        agent=ScriptedAgent(edits=[CODE, CODE]),
        agents={Producer.DOCUMENTER: ScriptedAgent(edits=[README])},
        planner=ScriptedPlanner((TASK,)),
    )

    memory = world.memory
    tip = memory.branches[world.workspace.run_branch]
    docs = [
        c for c in map(memory.commits.get, memory.ancestors(tip)) if c and c.subject[:5] == "docs:"
    ]
    diary = docs[0].tree["docs/mudancas/t1-diario.md"]
    assert diary.startswith("# Diário de bordo: t1\n")
    assert "## Tentativa `t1-a1` da etapa `t1-s`: rejeitada" in diary
    assert "> Split the long function in two." in diary
    assert "## Tentativa `t1-a2` da etapa `t1-s`: aprovada" in diary
    assert "t1-da1" not in diary


class Masking(ScriptedAgent):
    """A documenter whose runner redacts like the real one."""

    def redact_diary(self, diary: str) -> str:
        return redacted_diary(diary, Redactor())


def test_the_diary_in_the_branch_has_no_secret_and_keeps_the_rest_of_the_text(
    world: MemoryWorld,
) -> None:
    token = "ghp_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"
    world.run(
        measurer=ScriptedMeasurer(verdicts=(REJECTED, PASSED, PASSED)),
        agent=ScriptedAgent(edits=[CODE, CODE], reason=f"I used the key {token} to split f."),
        agents={Producer.DOCUMENTER: Masking(edits=[README])},
        planner=ScriptedPlanner((TASK,)),
    )

    memory = world.memory
    tip = memory.branches[world.workspace.run_branch]
    docs = [
        c for c in map(memory.commits.get, memory.ancestors(tip)) if c and c.subject[:5] == "docs:"
    ]
    diary = docs[0].tree["docs/mudancas/t1-diario.md"]
    assert token not in diary
    assert "> I used the key " in diary and " to split f." in diary
    assert "## Tentativa `t1-a2` da etapa `t1-s`: aprovada" in diary
