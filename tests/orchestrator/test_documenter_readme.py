"""The README is the documenter's to fix when it fails: told in its package, committed apart."""

from pathlib import Path

import pytest

from forja.core.artifacts.models import Producer
from forja.core.gates import PipelineOutcome
from forja.orchestrator.ports import AttemptContext, Expectations, PlannedTask, SinkFactory
from tests.orchestrator.fakes import ScriptedAgent, ScriptedMeasurer, ScriptedPlanner
from tests.orchestrator.harness import MemoryWorld

TASK = PlannedTask(
    "reduce the complexity of f",
    ("src/a.py",),
    8,
    400,
    stages=(Producer.IMPLEMENTER, Producer.DOCUMENTER),
)
CODE = {"src/a.py": "def f():\n    return 1\n"}
README = {"README.md": "# a\n\nGo.\n"}
REPORT = "- the build section cites make build; the project runs go build"


class Reporting(ScriptedMeasurer):
    seen: list[str]

    async def readme_report(self, ctx: AttemptContext) -> str:
        return REPORT

    async def judge(
        self, ctx: AttemptContext, sinks: SinkFactory, expectations: Expectations | None = None
    ) -> PipelineOutcome:
        self.seen = [*getattr(self, "seen", []), ctx.readme]
        return await super().judge(ctx, sinks, expectations)


@pytest.fixture
def world(tmp_path: Path) -> MemoryWorld:
    return MemoryWorld(tmp_path)


def run(world: MemoryWorld, measurer: ScriptedMeasurer, readme: dict[str, str]) -> None:
    world.run(
        measurer=measurer,
        agent=ScriptedAgent(edits=[CODE]),
        agents={Producer.DOCUMENTER: ScriptedAgent(edits=[readme])},
        planner=ScriptedPlanner((TASK,)),
    )


def subjects(world: MemoryWorld) -> list[str]:
    memory = world.memory
    tip = memory.branches[world.workspace.run_branch]
    return [memory.commits[sha].subject for sha in memory.ancestors(tip)]


def test_the_readme_the_documenter_fixed_is_a_commit_of_its_own_before_the_stage_ends(
    world: MemoryWorld,
) -> None:
    run(world, ScriptedMeasurer(), README)

    memory = world.memory
    stage = next(c for c in memory.commits.values() if c.subject.startswith("docs: "))
    readme = memory.commits[stage.parents[0]]
    assert readme.subject == "docs(readme): reduce the complexity of f"
    assert not dict(readme.trailers).get("Stage-Id")
    assert dict(stage.trailers)["Stage-Id"] == "t1-d"


def test_without_a_readme_change_there_is_no_readme_commit(world: MemoryWorld) -> None:
    run(world, ScriptedMeasurer(), {"docs/guide.md": "guide\n"})

    assert not [s for s in subjects(world) if s.startswith("docs(readme)")]


def test_what_is_wrong_with_the_readme_reaches_the_documenter_stage(world: MemoryWorld) -> None:
    measurer = Reporting()

    run(world, measurer, README)

    assert measurer.seen == ["", REPORT]
