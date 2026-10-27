"""Gate 11: the base measured twice per case, kept outside the worktree, and read back."""

import asyncio
import os
import sys
from pathlib import Path

import pytest

from forja.checks.base import Undecided
from forja.checks.differential_base import (
    INDEX,
    BaseCase,
    DifferentialBase,
    load,
    measure_base,
    save,
)
from forja.checks.differential_inputs import MissingInput
from forja.checks.tooling import Tools
from forja.core.events import EventLog
from forja.core.policy.differential import (
    EXIT_CODE,
    FILE,
    IGNORE,
    STDOUT,
    DifferentialCase,
    DifferentialOutput,
)
from forja.core.states import ExecutionState, Level
from tests.checks.support import RUN, sinks
from tests.core.events.support import FakeClock

COUNTING = (
    "import pathlib, sys; p = pathlib.Path(sys.argv[1]); "
    "n = int(p.read_text()) + 1 if p.exists() else 1; p.write_text(str(n)); print('run', n)"
)


@pytest.fixture
def log(tmp_path: Path) -> EventLog:
    opened = EventLog.open(tmp_path / "events.jsonl", RUN, clock=FakeClock())
    opened.append_transition(Level.EXECUTION, RUN, None, ExecutionState.PREPARING)
    return opened


def tools(log: EventLog, tmp_path: Path) -> Tools:
    return Tools(
        sinks=sinks,
        log=log,
        level=Level.EXECUTION,
        target=RUN,
        logs=tmp_path / "logs",
        host_env=dict(os.environ),
    )


def measure(
    log: EventLog, tmp_path: Path, *cases: DifferentialCase
) -> tuple[DifferentialBase, Path]:
    work, directory = tmp_path / "work", tmp_path / "data" / "differential"
    work.mkdir(exist_ok=True)
    base = asyncio.run(measure_base(tools(log, tmp_path), cases, work, directory, {}))
    return base, directory


def steady(name: str = "s") -> DifferentialCase:
    return DifferentialCase(name, (sys.executable, "-c", "print('same')"))


def counting(tmp_path: Path, *outputs: DifferentialOutput) -> DifferentialCase:
    command = (sys.executable, "-c", COUNTING, str(tmp_path / "counter"))
    return DifferentialCase("c", command, outputs or (DifferentialOutput(STDOUT),))


def test_a_steady_case_is_measured_twice_and_is_not_quarantined(
    log: EventLog, tmp_path: Path
) -> None:
    base, _ = measure(log, tmp_path, steady())

    shown = base.cases["s"]
    assert shown.outputs == {(STDOUT, ""): b"same\n", (EXIT_CODE, ""): b"0"}
    assert len(shown.durations) == 2
    assert not shown.quarantined


def test_a_case_whose_two_runs_differ_is_quarantined_on_that_output(
    log: EventLog, tmp_path: Path
) -> None:
    base, _ = measure(log, tmp_path, counting(tmp_path, DifferentialOutput(STDOUT)))

    assert base.cases["c"].unstable == ("stdout",)
    assert base.cases["c"].quarantined
    assert base.cases["c"].outputs[(STDOUT, "")] == b"run 1\n"  # the first run is kept


def test_the_rule_of_the_case_decides_what_counts_as_unstable(
    log: EventLog, tmp_path: Path
) -> None:
    excused = DifferentialOutput(STDOUT, IGNORE, ignore=("^run",))

    base, _ = measure(log, tmp_path, counting(tmp_path, excused))

    assert not base.cases["c"].quarantined


def test_only_the_output_that_differed_is_named(log: EventLog, tmp_path: Path) -> None:
    both = (DifferentialOutput(STDOUT), DifferentialOutput(EXIT_CODE))

    base, _ = measure(log, tmp_path, counting(tmp_path, *both))

    assert base.cases["c"].unstable == ("stdout",)


def test_the_base_is_written_outside_the_worktree_and_read_back(
    log: EventLog, tmp_path: Path
) -> None:
    written = DifferentialCase(
        "w",
        (sys.executable, "-c", "open('r.bin', 'wb').write(bytes([0, 255]))"),
        (DifferentialOutput(FILE, path="r.bin"), DifferentialOutput(FILE, path="none.bin")),
    )
    base, directory = measure(log, tmp_path, steady(), written)

    assert (directory / INDEX).is_file()
    assert not any(directory in p.parents for p in (tmp_path / "work").rglob("*"))
    assert load(directory, [steady(), written]) == base


def test_a_frozen_input_is_kept_and_read_back(log: EventLog, tmp_path: Path) -> None:
    (tmp_path / "work").mkdir()
    (tmp_path / "work" / "in.txt").write_bytes(b"data\n")
    case = DifferentialCase(
        "i", (sys.executable, "-c", "import sys; print(sys.stdin.read(), end='')"), stdin="in.txt"
    )

    base, directory = measure(log, tmp_path, case)

    assert base.cases["i"].outputs[(STDOUT, "")] == b"data\n"
    assert load(directory, [case]) == base
    assert base.inputs["i"].parent == directory / "inputs"


def test_a_missing_input_writes_nothing(log: EventLog, tmp_path: Path) -> None:
    case = DifferentialCase("i", (sys.executable, "-c", "pass"), stdin="absent.txt")

    with pytest.raises(MissingInput):
        measure(log, tmp_path, case)

    assert not (tmp_path / "data").exists()


def test_a_run_that_cannot_be_made_writes_nothing(log: EventLog, tmp_path: Path) -> None:
    broken = DifferentialCase("b", (str(tmp_path / "no-such-program"),))

    with pytest.raises(Undecided):
        measure(log, tmp_path, steady(), broken)

    assert not (tmp_path / "data" / "differential" / INDEX).exists()


def test_a_directory_without_an_index_is_not_a_base(tmp_path: Path) -> None:
    assert load(tmp_path / "nothing", [steady()]) is None


def test_a_base_made_for_other_cases_is_not_taken(log: EventLog, tmp_path: Path) -> None:
    _, directory = measure(log, tmp_path, steady("one"))

    assert load(directory, [steady("two")]) is None
    assert load(directory, [steady("one"), steady("two")]) is None


def test_an_unreadable_index_is_not_a_base(log: EventLog, tmp_path: Path) -> None:
    _, directory = measure(log, tmp_path, steady())
    (directory / INDEX).write_text("{", encoding="utf-8")

    assert load(directory, [steady()]) is None


def test_a_base_missing_an_output_file_is_not_a_base(log: EventLog, tmp_path: Path) -> None:
    _, directory = measure(log, tmp_path, steady())
    next((directory / "outputs").iterdir()).unlink()

    assert load(directory, [steady()]) is None


def test_memory_peaks_are_kept_only_when_measured(tmp_path: Path) -> None:
    case = BaseCase({(STDOUT, ""): b"x"}, (0.5, 0.7), (100, 120))
    bare = BaseCase({(STDOUT, ""): None}, (0.1, 0.2))
    directory = tmp_path / "d"
    save(DifferentialBase({"a": case, "b": bare}), directory)

    loaded = load(directory, [steady("a"), steady("b")])

    assert loaded is not None
    assert loaded.cases == {"a": case, "b": bare}
