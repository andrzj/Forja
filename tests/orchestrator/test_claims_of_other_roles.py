"""The cycle hands the claims of the implementer and the test author to the measurer."""

from pathlib import Path

from forja.core.artifacts.llm_output import Claim, FileCitation
from forja.core.artifacts.models import Producer
from forja.orchestrator.ports import Expectations, PlannedTask
from tests.orchestrator.fakes import ScriptedAgent, ScriptedMeasurer, ScriptedPlanner
from tests.orchestrator.harness import MemoryWorld

CLAIM = Claim(
    statement="the loop is gone",
    citations=(FileCitation(kind="file", path="src/a.py", line_start=1, line_end=2),),
)
CODE = {"src/a.py": "def f():\n    return 1\n"}


def expected_for(tmp_path: Path, claims: tuple[Claim, ...]) -> list[Expectations | None]:
    measurer = ScriptedMeasurer()
    MemoryWorld(tmp_path).run(
        measurer=measurer,
        agent=ScriptedAgent(edits=[CODE], claims=claims),
        planner=ScriptedPlanner(
            (PlannedTask("x", ("src/a.py",), 8, 400, (Producer.IMPLEMENTER,)),)
        ),
    )
    return measurer.expected


def test_what_the_implementer_states_goes_to_the_measurer(tmp_path: Path) -> None:
    expected = expected_for(tmp_path, (CLAIM,))

    assert expected[0] is not None
    assert expected[0].claims == (CLAIM,)


def test_an_implementer_that_states_nothing_owes_nothing(tmp_path: Path) -> None:
    assert expected_for(tmp_path, ())[0] is None
