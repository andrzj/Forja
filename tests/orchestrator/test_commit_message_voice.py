"""The reason the agent gives reaches the measurer as the message of the commit to come."""

from pathlib import Path

import pytest

from forja.core.gates import PipelineOutcome
from forja.orchestrator.ports import AttemptContext, Expectations, SinkFactory
from tests.orchestrator.fakes import PASSED, ScriptedAgent, ScriptedMeasurer, ScriptedPlanner
from tests.orchestrator.harness import MemoryWorld


class Watching(ScriptedMeasurer):
    seen: list[str]

    async def judge(
        self, ctx: AttemptContext, sinks: SinkFactory, expectations: Expectations | None = None
    ) -> PipelineOutcome:
        self.seen = [*getattr(self, "seen", []), ctx.message]
        return await super().judge(ctx, sinks, expectations)


@pytest.fixture
def world(tmp_path: Path) -> MemoryWorld:
    return MemoryWorld(tmp_path)


def test_the_agents_reason_is_what_the_measurer_reads_as_the_commit_message(
    world: MemoryWorld,
) -> None:
    measurer = Watching(verdicts=(PASSED,))

    world.run(
        measurer=measurer,
        agent=ScriptedAgent(
            edits=[{"src/a.py": "def f():\n    return 1\n"}], reason="Why it is so."
        ),
        planner=ScriptedPlanner(),
    )

    assert measurer.seen == ["Why it is so."]
