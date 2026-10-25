"""The archaeologist is the first stage of an investigation: it writes no file, the Forja stores
what it declared sorted by what it rests on, and the documenter writes from that."""

import asyncio
from dataclasses import dataclass
from pathlib import Path

import pytest

from forja.core.artifacts.llm_output import Claim, EvidenceCitation, FactCitation, FileCitation
from forja.core.artifacts.models import ArtifactType, Assumption, Producer
from forja.core.artifacts.schemas import Basis, FindingsBody
from forja.core.artifacts.store import ArtifactStore
from forja.core.events import EventLog
from forja.core.states import AttemptState, ExecutionState, Level, StageState, TaskState
from forja.orchestrator.config import Budget, Objective
from forja.orchestrator.outcome import Outcome
from forja.orchestrator.phases import SUMMARY_NAME
from forja.orchestrator.planner import InvestigationPlanner
from forja.orchestrator.ports import Baseline, Expectations, PlannedTask
from forja.orchestrator.summary import read_facts
from tests.orchestrator.fakes import (
    PASSED,
    REJECTED,
    ScriptedAgent,
    ScriptedMeasurer,
    ScriptedPlanner,
)
from tests.orchestrator.harness import MemoryWorld

QUESTION = "how does the page size reach the query?"
BY_FILE = Claim(
    statement="the page size is read from the settings",
    citations=(FileCitation(kind="file", path="src/a.py", line_start=1, line_end=2),),
)
BY_FACT = Claim(
    statement="the page size is 10",
    citations=(FactCitation(kind="fact", fact_id="f1"),),
)
BY_BOTH = Claim(
    statement="the query uses it",
    citations=(
        FileCitation(kind="file", path="src/a.py", line_start=1, line_end=2),
        FactCitation(kind="fact", fact_id="f1"),
        EvidenceCitation(kind="evidence", evidence_id="lint_violations"),
    ),
)
GUESS = Assumption(
    statement="pages start at 1", reason="no test shows it", missing_evidence="a test"
)
NOTHING: list[dict[str, str]] = [{}]
DOCS = {"docs/page-size.md": "# Page size\n"}


@pytest.fixture
def world(tmp_path: Path) -> MemoryWorld:
    found = MemoryWorld(tmp_path)
    found.config = found.config.model_copy(
        update={"objective": Objective.INVESTIGATE, "question": QUESTION}
    )
    return found


@dataclass
class Run:
    outcome: Outcome
    log: EventLog
    archaeologist: ScriptedAgent
    documenter: ScriptedAgent


def run(
    world: MemoryWorld,
    measurer: ScriptedMeasurer | None = None,
    archaeologist: ScriptedAgent | None = None,
) -> Run:
    archaeologist = archaeologist or ScriptedAgent(edits=NOTHING, claims=(BY_FILE,))
    documenter = ScriptedAgent(edits=[DOCS])
    outcome, log = world.run(
        measurer=measurer or ScriptedMeasurer(),
        agent=ScriptedAgent(edits=NOTHING),
        agents={Producer.ARCHAEOLOGIST: archaeologist, Producer.DOCUMENTER: documenter},
        planner=ScriptedPlanner(
            (
                PlannedTask(
                    QUESTION, ("src/a.py",), 8, 400, (Producer.ARCHAEOLOGIST, Producer.DOCUMENTER)
                ),
            )
        ),
    )
    return Run(outcome, log, archaeologist, documenter)


def test_an_investigation_is_one_task_of_the_archaeologist_and_the_documenter() -> None:
    planned = asyncio.run(
        InvestigationPlanner(QUESTION, ("src",)).plan(Path("."), Baseline(True), Budget())
    )

    assert len(planned) == 1
    assert planned[0].intent == QUESTION
    assert planned[0].scope == ("src",)
    assert planned[0].stages == (Producer.ARCHAEOLOGIST, Producer.DOCUMENTER)


def test_the_stages_run_in_order_and_the_archaeologist_has_its_own_ids(world: MemoryWorld) -> None:
    done = run(world)

    state = done.log.state
    assert done.outcome.state is ExecutionState.DELIVERED
    assert state.children_of(Level.STAGE, "t1") == ["t1-f", "t1-d"]
    assert state.children_of(Level.ATTEMPT, "t1-f") == ["t1-fa1"]
    assert state.state_of(Level.STAGE, "t1-f") is StageState.COMMITTED
    assert state.state_of(Level.ATTEMPT, "t1-fa1") is AttemptState.COMMITTED
    assert state.state_of(Level.TASK, "t1") is TaskState.INTEGRATED


def test_the_archaeologist_commits_nothing_and_the_documenter_commits_once(
    world: MemoryWorld,
) -> None:
    run(world)

    memory = world.memory
    tip = memory.branches[world.workspace.run_branch]
    kinds = [memory.commits[sha].subject.split(":")[0] for sha in memory.ancestors(tip)]
    assert kinds.count("docs") == 1
    assert "fix" not in kinds
    assert "refactor" not in kinds


def test_the_findings_are_stored_by_the_forja_with_the_basis_it_gave_each_claim(
    world: MemoryWorld,
) -> None:
    agent = ScriptedAgent(edits=NOTHING, claims=(BY_FILE, BY_FACT, BY_BOTH), assumptions=(GUESS,))

    run(world, archaeologist=agent)

    stored = ArtifactStore(world.run_dir / "store").get("findings-t1")
    assert stored.header.type is ArtifactType.FINDINGS
    assert stored.header.producer is Producer.ARCHAEOLOGIST
    assert stored.header.attempt_id == "t1-fa1"
    assert stored.header.assumptions == (GUESS,)
    assert isinstance(stored.body, FindingsBody)
    assert [(c.statement, c.basis) for c in stored.body.claims] == [
        (BY_FILE.statement, Basis.PROVEN),
        (BY_FACT.statement, Basis.CONFIRMED),
        (BY_BOTH.statement, Basis.CONFIRMED),
    ]


def test_the_documenter_is_told_the_findings_in_three_kinds(world: MemoryWorld) -> None:
    agent = ScriptedAgent(edits=NOTHING, claims=(BY_FILE, BY_FACT), assumptions=(GUESS,))

    done = run(world, archaeologist=agent)

    told = done.documenter.seen[0].findings
    proven, confirmed, premises = told.split("### ")[1:]
    assert "src/a.py:1-2" in proven
    assert BY_FILE.statement in proven
    assert BY_FACT.statement not in proven
    assert "fact f1" in confirmed
    assert BY_FACT.statement in confirmed
    assert GUESS.statement in premises
    assert "a test" in premises
    assert done.archaeologist.seen[0].findings == ""


def test_the_premises_of_the_archaeologist_reach_the_summary_as_premises(
    world: MemoryWorld,
) -> None:
    agent = ScriptedAgent(edits=NOTHING, claims=(BY_FILE,), assumptions=(GUESS,))

    done = run(world, archaeologist=agent)

    premise = read_facts(done.log.path).premises[0]
    assert (premise.task, premise.stage, premise.statement) == ("t1", "t1-f", GUESS.statement)


def test_the_measurer_is_told_the_claims_to_check_and_no_criteria(world: MemoryWorld) -> None:
    measurer = ScriptedMeasurer()

    run(world, measurer, ScriptedAgent(edits=NOTHING, claims=(BY_FILE,)))

    expected = measurer.expected[0]
    assert isinstance(expected, Expectations)
    assert expected.claims == (BY_FILE,)
    assert expected.elements == ()
    assert expected.specified == ()


def test_an_archaeologist_rejected_by_a_gate_is_tried_again_and_only_the_good_one_is_stored(
    world: MemoryWorld,
) -> None:
    done = run(world, ScriptedMeasurer(verdicts=(REJECTED, PASSED)))

    state = done.log.state
    assert done.outcome.state is ExecutionState.DELIVERED
    assert state.children_of(Level.ATTEMPT, "t1-f") == ["t1-fa1", "t1-fa2"]
    assert state.state_of(Level.ATTEMPT, "t1-fa1") is AttemptState.REJECTED
    assert ArtifactStore(world.run_dir / "store").header("findings-t1").attempt_id == "t1-fa2"


def test_an_archaeologist_that_never_passes_blocks_the_task_before_the_documenter(
    world: MemoryWorld,
) -> None:
    done = run(world, ScriptedMeasurer(verdicts=(REJECTED,)))

    state = done.log.state
    assert state.state_of(Level.TASK, "t1") is TaskState.BLOCKED
    assert state.state_of(Level.STAGE, "t1-f") is StageState.EXHAUSTED
    assert not state.has_target(Level.STAGE, "t1-d")


def test_the_summary_of_an_investigation_names_what_rests_on_a_premise(
    world: MemoryWorld,
) -> None:
    agent = ScriptedAgent(edits=NOTHING, claims=(BY_FILE,), assumptions=(GUESS,))

    run(world, archaeologist=agent)

    text = (world.run_dir / SUMMARY_NAME).read_text(encoding="utf-8")
    assert "Commits com `Stage-Id: t1-d`." in text
    assert "t1-f`" not in text.split("## Tarefas bloqueadas")[0].split("Commits com")[1]
    assert "Nenhuma: esta execução só investiga e documenta." in text
    assert "Quem investiga:" in text
    assert "Quem documenta: o mesmo que investiga" in text
