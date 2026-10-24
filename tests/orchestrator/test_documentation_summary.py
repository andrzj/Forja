"""The summary says what each integrated task's documenter left in the repository."""

from pathlib import Path

import pytest

from forja.core.artifacts.models import Producer
from forja.orchestrator.phases import SUMMARY_NAME
from forja.orchestrator.ports import PlannedTask
from forja.orchestrator.summary import Documented, Facts, read_facts, render_summary
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
README = {"README.md": "# a\n\nf returns 1.\n"}
NOT_CHECKED = "Não conferido: links externos do README"


@pytest.fixture
def world(tmp_path: Path) -> MemoryWorld:
    return MemoryWorld(tmp_path)


def _run(world: MemoryWorld, documented: list[str]) -> tuple[str, Path]:
    """The summary text and the path of the log of a run whose documenter changed these files."""
    measurer = ScriptedMeasurer()
    measurer.documented = documented  # type: ignore[attr-defined]
    _, log = world.run(
        measurer=measurer,
        agent=ScriptedAgent(edits=[CODE]),
        agents={Producer.DOCUMENTER: ScriptedAgent(edits=[README])},
        planner=ScriptedPlanner((TASK,)),
    )
    return (world.run_dir / SUMMARY_NAME).read_text(encoding="utf-8"), log.path


def _summary(world: MemoryWorld, documented: list[str]) -> str:
    return _run(world, documented)[0]


def test_the_summary_lists_the_record_the_readme_and_the_decision_records(
    world: MemoryWorld,
) -> None:
    text = _summary(world, ["README.md", "docs/adr/0025-x.md", "docs/guia.md"])

    assert (
        "- `t1`: registro `docs/mudancas/t1.md`; README: `README.md`; "
        "ADR: `docs/adr/0025-x.md`; outros: `docs/guia.md`." in text
    )
    assert NOT_CHECKED in text


def test_a_documenter_that_changed_only_the_record_is_said_so(world: MemoryWorld) -> None:
    text = _summary(world, [])

    assert "- `t1`: registro `docs/mudancas/t1.md`." in text


def test_a_run_without_a_documenter_has_nothing_to_say_about_documentation(
    world: MemoryWorld,
) -> None:
    world.run(planner=ScriptedPlanner(()), measurer=ScriptedMeasurer(metrics={}))

    text = (world.run_dir / SUMMARY_NAME).read_text(encoding="utf-8")
    assert "## Documentação\n\nNenhuma tarefa integrada com documentação.\n" in text
    assert NOT_CHECKED not in text


def test_the_facts_come_from_the_log_and_the_last_note_of_a_task_wins(
    world: MemoryWorld,
) -> None:
    _, log_path = _run(world, ["README.md"])

    facts = read_facts(log_path)

    assert facts.documented == {"t1": Documented("docs/mudancas/t1.md", ("README.md",))}


def test_a_task_that_was_not_integrated_is_not_listed(world: MemoryWorld) -> None:
    _, log = world.run()
    facts = Facts(documented={"nope": Documented("docs/mudancas/nope.md", ())})

    text = render_summary(log.state, facts, world.config, "b", Path("x"))

    assert "nope" not in text
