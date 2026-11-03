"""Gate 11 in the summary: what the base showed about its cases, said through the log."""

from pathlib import Path

from forja.checks.differential_base import BaseCase, DifferentialBase
from forja.core.events import EventLog
from forja.core.policy.differential import STDOUT
from forja.core.states import Level
from forja.orchestrator.config import RunConfig
from forja.orchestrator.summary import (
    DIFFERENTIAL,
    Facts,
    differential_note,
    read_facts,
    render_summary,
)
from tests.checks.support import RUN
from tests.core.events.support import FakeClock

OUT: dict[tuple[str, str], bytes | None] = {(STDOUT, ""): b"x"}


def case(*, unstable: tuple[str, ...] = (), memories: tuple[int, ...] = (1, 2)) -> BaseCase:
    return BaseCase(OUT, (0.1, 0.2), memories, unstable)


def base_of(**cases: BaseCase) -> DifferentialBase:
    return DifferentialBase(dict(cases))


def config() -> RunConfig:
    return RunConfig.model_validate(
        {
            "repo": "r",
            "base_commit": "c" * 40,
            "objective": "refactor",
            "implementer": {"name": "claude-code", "path": "p", "version": "1"},
            "forja_version": "0",
            "policy_version": "0",
        }
    )


def summary_with(tmp_path: Path, note: dict[str, object]) -> str:
    log = EventLog.open(tmp_path / "e.jsonl", RUN, clock=FakeClock())
    facts = Facts(differential={k: v for k, v in note.items()})  # type: ignore[misc]
    return render_summary(log.state, facts, config(), "b", Path("x"))


def test_a_base_with_nothing_to_say_has_empty_lists() -> None:
    note = differential_note(base_of(a=case(), b=case()))

    assert note == {
        "quarantined": [],
        "quarantined_count": 0,
        "unmeasured": [],
        "unmeasured_count": 0,
    }


def test_the_cases_in_quarantine_and_the_ones_without_memory_are_named_apart() -> None:
    note = differential_note(
        base_of(steady=case(), held=case(unstable=("stdout",)), bare=case(memories=()))
    )

    assert note["quarantined"] == ["held"]
    assert note["unmeasured"] == ["bare"]


def test_a_note_holds_ten_names_cut_short_and_counts_all_of_them() -> None:
    cases = {f"c{n:02d}": case(unstable=("stdout",)) for n in range(11)}
    cases["l" * 90] = case(unstable=("stdout",))

    note = differential_note(DifferentialBase(cases))

    assert note["quarantined_count"] == 12
    names = note["quarantined"]
    assert isinstance(names, list) and len(names) == 10
    assert names[0] == "c00" and all(len(str(n)) <= 40 for n in names)
    assert ("l" * 40) not in names  # sorted, so it is past the tenth


def test_the_name_of_a_case_is_cut_to_forty_characters() -> None:
    note = differential_note(base_of(**{"l" * 90: case(unstable=("stdout",))}))

    assert note["quarantined"] == ["l" * 40]


def test_the_summary_says_which_cases_were_not_judged(tmp_path: Path) -> None:
    text = summary_with(
        tmp_path,
        {
            "quarantined": ["held", "other"],
            "quarantined_count": 5,
            "unmeasured": [],
            "unmeasured_count": 0,
        },
    )

    assert (
        "- **Teste diferencial: os casos `held`, `other` e mais 3 ficaram em quarentena "
        "(saídas instáveis na base) e não foram julgados.**"
    ) in text
    assert "memória" not in text


def test_the_summary_says_which_cases_had_no_memory_measure(tmp_path: Path) -> None:
    text = summary_with(
        tmp_path,
        {"quarantined": [], "quarantined_count": 0, "unmeasured": ["bare"], "unmeasured_count": 1},
    )

    assert (
        "- **Teste diferencial: os casos `bare` ficaram sem medida de memória "
        "(a plataforma não mede); só saídas e tempo.**"
    ) in text
    assert "quarentena" not in text


def test_without_a_note_the_summary_says_nothing_of_the_cases(tmp_path: Path) -> None:
    assert "Teste diferencial" not in summary_with(tmp_path, {})


def test_the_last_note_of_the_log_is_the_one_the_summary_reads(tmp_path: Path) -> None:
    log = EventLog.open(tmp_path / "e.jsonl", RUN, clock=FakeClock())
    first = differential_note(base_of(a=case(unstable=("stdout",))))
    second = differential_note(base_of(a=case()))
    log.append_progress(Level.EXECUTION, RUN, DIFFERENTIAL, payload=first)
    log.append_progress(Level.EXECUTION, RUN, DIFFERENTIAL, payload=second)

    assert read_facts(log.path).differential == second
