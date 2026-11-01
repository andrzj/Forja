"""Facts a person recorded: the file, the premises they settle and where they reach the agents."""

from pathlib import Path

import pytest

from forja.core.artifacts.models import Assumption, Producer
from forja.core.redaction import Redactor
from forja.orchestrator.agent_runner import build_package
from forja.orchestrator.facts import Fact, FactsError, parse_facts
from forja.orchestrator.phases import SUMMARY_NAME
from forja.orchestrator.ports import AttemptContext, TaskInfo
from forja.orchestrator.summary import Premise
from tests.orchestrator.fakes import ScriptedAgent, ScriptedMeasurer
from tests.orchestrator.harness import MemoryWorld

GUESS = Assumption(
    statement="pages hold 10 items", reason="the report says nothing", missing_evidence="page size"
)
CODE = {"src/a.py": "def f():\n    return 1\n"}
README = {"README.md": "# a\n"}


def test_a_facts_file_is_read_line_by_line_and_skips_blanks_and_comments() -> None:
    text = (
        "# facts of the team\n\n"
        "F1 | Ana | 2026-10-20 | the page size is 10\n"
        "F2 | Rui | 2026-10-21 | it is a bug | corrige:pabcdef12\n"
        "F3 | Rui | 2026-10-22 | yes | confirma:p01234567\n"
    )

    facts = parse_facts(text)

    assert [f.id for f in facts] == ["F1", "F2", "F3"]
    assert facts[0] == Fact(id="F1", author="Ana", date="2026-10-20", text="the page size is 10")
    assert (facts[1].relation, facts[1].premise) == ("corrects", "pabcdef12")
    assert (facts[2].relation, facts[2].premise) == ("confirms", "p01234567")


@pytest.mark.parametrize(
    ("line", "complaint"),
    [
        ("F1 | Ana | 2026-10-20", "linha 1: use `id | autor | data | texto`"),
        ("F1 | Ana | 2026-10-20 | ", "linha 1: use"),
        ("F 1 | Ana | 2026-10-20 | x", "o id `F 1` só pode ter"),
        ("F1 | Ana | 20/10/2026 | x", "não é AAAA-MM-DD"),
        ("F1 | Ana | 2026-10-20 | x | talvez:p01234567", "não é `confirma:<id>`"),
        ("F1 | Ana | 2026-10-20 | x | confirma:5", "não é `confirma:<id>`"),
    ],
)
def test_a_line_that_cannot_be_used_is_named(line: str, complaint: str) -> None:
    with pytest.raises(FactsError, match=complaint):
        parse_facts(line)


def test_the_same_id_twice_is_refused() -> None:
    with pytest.raises(FactsError, match="linha 2: o fato `F1` aparece duas vezes"):
        parse_facts("F1 | Ana | 2026-10-20 | a\nF1 | Rui | 2026-10-21 | b")


def test_a_premise_has_the_same_name_every_time_and_another_name_for_another_thing() -> None:
    one = Premise("t1", "t1-a1", "", "t1-s", "pages hold 10 items", "r", "m")
    again = Premise("t1", "t1-a2", "", "t1-s", "pages hold 10 items", "other", "other")

    assert one.id == again.id
    assert one.id.startswith("p") and len(one.id) == 9
    assert one.id != Premise("t2", "t2-a1", "", "t2-s", "pages hold 10 items").id
    assert one.id != Premise("t1", "t1-a1", "", "t1-s", "pages hold 20 items").id
    assert Premise("t1", "t1-a1", "complexity").id != one.id


def package_with(tmp_path: Path, facts: tuple[Fact, ...]) -> str:
    task = TaskInfo("t1", "t1-s", "reduce f", (), 3, 120, Producer.IMPLEMENTER)
    ctx = AttemptContext(task, "t1-a1", tmp_path, None, facts=facts)
    return build_package(ctx, Redactor())


def test_the_recorded_facts_reach_the_package_with_how_to_cite_them(tmp_path: Path) -> None:
    fact = Fact(id="F1", author="Ana", date="2026-10-20", text="the page size is 10")

    text = package_with(tmp_path, (fact,))

    assert "## Facts a person recorded" in text
    assert "- `F1` (Ana, 2026-10-20): the page size is 10" in text
    assert '"fact_id": "<id>"' in text


def test_a_package_with_no_facts_says_nothing_of_them(tmp_path: Path) -> None:
    assert "Facts a person recorded" not in package_with(tmp_path, ())


def test_a_secret_in_a_fact_is_redacted_before_the_agent_sees_it(tmp_path: Path) -> None:
    secret = "ghp_" + "A1b2C3d4" * 5
    fact = Fact(id="F1", author="Ana", date="2026-10-20", text=f"the key is {secret}")

    assert secret not in package_with(tmp_path, (fact,))


@pytest.fixture
def world(tmp_path: Path) -> MemoryWorld:
    return MemoryWorld(tmp_path)


def test_a_guess_of_the_agent_is_a_premise_with_the_commits_that_rest_on_it(
    world: MemoryWorld,
) -> None:
    from forja.core.artifacts.models import Producer  # noqa: PLC0415
    from forja.orchestrator.ports import PlannedTask  # noqa: PLC0415
    from tests.orchestrator.fakes import ScriptedPlanner  # noqa: PLC0415

    task = PlannedTask(
        "reduce f", ("src/a.py",), 8, 400, stages=(Producer.IMPLEMENTER, Producer.DOCUMENTER)
    )
    world.run(
        measurer=ScriptedMeasurer(),
        agent=ScriptedAgent(edits=[CODE], assumptions=(GUESS,)),
        agents={Producer.DOCUMENTER: ScriptedAgent(edits=[README])},
        planner=ScriptedPlanner((task,)),
    )

    text = (world.run_dir / SUMMARY_NAME).read_text(encoding="utf-8")
    name = Premise("t1", "", "", statement=GUESS.statement).id
    assert (
        f"- `{name}` pages hold 10 items (por quê: the report says nothing; evidência que "
        "faltou: page size); tarefa `t1`, tentativa `t1-a1`. "
        "Commits com `Stage-Id: t1-s`, `Stage-Id: t1-d`."
    ) in text


def test_a_fact_that_settles_a_premise_changes_its_line_and_one_that_settles_none_is_said(
    world: MemoryWorld,
) -> None:
    name = Premise("t1", "", "", statement=GUESS.statement).id
    world.config = world.config.model_copy(
        update={
            "facts": (
                Fact(
                    id="F1",
                    author="Ana",
                    date="2026-10-20",
                    text="pages hold 25",
                    relation="corrects",
                    premise=name,
                ),
                Fact(
                    id="F2",
                    author="Rui",
                    date="2026-10-21",
                    text="x",
                    relation="confirms",
                    premise="p00000000",
                ),
            )
        }
    )

    world.run(measurer=ScriptedMeasurer(), agent=ScriptedAgent(edits=[CODE], assumptions=(GUESS,)))

    text = (world.run_dir / SUMMARY_NAME).read_text(encoding="utf-8")
    assert "Corrigida por `F1` (Ana, 2026-10-20): pages hold 25" in text
    assert "- O fato `F2` trata da premissa `p00000000`, que esta execução não teve." in text


def test_a_fact_that_names_no_premise_is_not_said_to_name_a_missing_one(
    world: MemoryWorld,
) -> None:
    world.config = world.config.model_copy(
        update={"facts": (Fact(id="F3", author="Ana", date="2026-10-22", text="a plain fact"),)}
    )

    world.run(measurer=ScriptedMeasurer(), agent=ScriptedAgent(edits=[CODE], assumptions=(GUESS,)))

    text = (world.run_dir / SUMMARY_NAME).read_text(encoding="utf-8")
    assert "`F3` trata da premissa" not in text


def test_a_premise_of_the_specifier_does_not_blame_its_own_stage_as_a_commit(
    world: MemoryWorld,
) -> None:
    from forja.core.artifacts.llm_output import Criterion, CriterionLevel  # noqa: PLC0415
    from forja.orchestrator.config import FixRequest, Objective  # noqa: PLC0415
    from forja.orchestrator.planner import FixPlanner  # noqa: PLC0415
    from tests.orchestrator.test_specifier import FixPlannerOf  # noqa: PLC0415

    fix = FixRequest(description="- page 1 is wrong")
    world.config = world.config.model_copy(update={"objective": Objective.FIX, "fix": fix})
    criteria = (Criterion(id=1, text="page 1 is right", level=CriterionLevel.UNIT, origin=("E1",)),)
    world.run(
        measurer=ScriptedMeasurer(),
        agent=ScriptedAgent(edits=[CODE]),
        agents={
            Producer.SPECIFIER: ScriptedAgent(edits=[{}], criteria=criteria, assumptions=(GUESS,)),
            Producer.TEST_AUTHOR: ScriptedAgent(edits=[{"tests/test_a.py": "def test_a(): ...\n"}]),
            Producer.DOCUMENTER: ScriptedAgent(edits=[README]),
        },
        planner=FixPlannerOf(FixPlanner(fix, ("src/a.py",), "tests")),
    )

    text = (world.run_dir / SUMMARY_NAME).read_text(encoding="utf-8")
    assert (
        "tentativa `t1-ca1`. Commits com `Stage-Id: t1-t`, `Stage-Id: t1-s`, `Stage-Id: t1-d`."
        in text
    )
