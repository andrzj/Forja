"""Gate 11: running one case and reading what it left."""

import asyncio
import os
import sys
from pathlib import Path

import pytest

from forja.checks.base import Undecided
from forja.checks.differential_run import CaseRun, run_case, stdout_of
from forja.checks.tooling import Tools
from forja.core.events import EventLog
from forja.core.gates import Inconclusive, InconclusiveReason
from forja.core.policy.differential import (
    EXIT_CODE,
    FILE,
    STDOUT,
    DifferentialCase,
    DifferentialOutput,
)
from forja.core.states import ExecutionState, Level
from tests.checks.support import RUN, sinks
from tests.core.events.support import FakeClock


@pytest.fixture
def log(tmp_path: Path) -> EventLog:
    opened = EventLog.open(tmp_path / "events.jsonl", RUN, clock=FakeClock())
    opened.append_transition(Level.EXECUTION, RUN, None, ExecutionState.PREPARING)
    return opened


def tools(log: EventLog, tmp_path: Path, timeouts: dict[str, float] | None = None) -> Tools:
    return Tools(
        sinks=sinks,
        log=log,
        level=Level.EXECUTION,
        target=RUN,
        logs=tmp_path / "logs",
        host_env=dict(os.environ),
        timeouts=timeouts,
    )


def case(code: str, *outputs: DifferentialOutput, cwd: str = "") -> DifferentialCase:
    kept = outputs or (DifferentialOutput(STDOUT), DifferentialOutput(EXIT_CODE))
    return DifferentialCase("c", (sys.executable, "-c", code), kept, cwd=cwd)


def run(
    log: EventLog, tmp_path: Path, spec: DifferentialCase, stdin: Path | None = None
) -> CaseRun:
    work = tmp_path / "work"
    work.mkdir(exist_ok=True)
    return asyncio.run(run_case(tools(log, tmp_path), spec, work, stdin, {}))


def test_stdout_and_exit_code_are_read(log: EventLog, tmp_path: Path) -> None:
    shown = run(
        log, tmp_path, case("import sys; print('a'); print('b', file=sys.stderr); sys.exit(3)")
    )

    assert shown.outputs == {(STDOUT, ""): b"a\n", (EXIT_CODE, ""): b"3"}


def test_a_failing_exit_code_is_a_value_not_a_failure(log: EventLog, tmp_path: Path) -> None:
    shown = run(log, tmp_path, case("raise SystemExit(1)"))

    assert shown.outputs[(EXIT_CODE, "")] == b"1"


def test_a_declared_file_is_read_and_a_missing_one_is_none(log: EventLog, tmp_path: Path) -> None:
    spec = case(
        "open('out/r.txt', 'wb').write(b'x\\r\\ny')",
        DifferentialOutput(FILE, path="out/r.txt"),
        DifferentialOutput(FILE, path="out/none.txt"),
    )
    (tmp_path / "work" / "out").mkdir(parents=True)

    shown = run(log, tmp_path, spec)

    assert shown.outputs == {(FILE, "out/r.txt"): b"x\r\ny", (FILE, "out/none.txt"): None}


def test_a_file_left_by_an_earlier_run_is_not_read_as_this_ones(
    log: EventLog, tmp_path: Path
) -> None:
    (tmp_path / "work" / "out").mkdir(parents=True)
    (tmp_path / "work" / "out" / "old.txt").write_bytes(b"from before")

    shown = run(log, tmp_path, case("pass", DifferentialOutput(FILE, path="out/old.txt")))

    assert shown.outputs == {(FILE, "out/old.txt"): None}
    assert not (tmp_path / "work" / "out" / "old.txt").exists()


def test_a_file_that_cannot_be_removed_is_not_decided(
    log: EventLog, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "work").mkdir()
    (tmp_path / "work" / "old.txt").write_bytes(b"x")

    def refuse(self: Path, *, missing_ok: bool = False) -> None:
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(Path, "unlink", refuse)
    with pytest.raises(Undecided) as info:
        run(log, tmp_path, case("pass", DifferentialOutput(FILE, path="old.txt")))

    assert isinstance(info.value.result, Inconclusive)
    assert "cannot remove old.txt: Permission denied" in (info.value.result.detail or "")


def test_a_declared_directory_is_left_alone(log: EventLog, tmp_path: Path) -> None:
    (tmp_path / "work" / "out").mkdir(parents=True)

    shown = run(log, tmp_path, case("pass", DifferentialOutput(FILE, path="out")))

    assert shown.outputs == {(FILE, "out"): None}
    assert (tmp_path / "work" / "out").is_dir()


def test_a_declared_file_outside_the_repository_is_none_and_untouched(
    log: EventLog, tmp_path: Path
) -> None:
    (tmp_path / "work").mkdir()
    (tmp_path / "outside.txt").write_bytes(b"not yours")

    shown = run(log, tmp_path, case("pass", DifferentialOutput(FILE, path="../outside.txt")))

    assert shown.outputs == {(FILE, "../outside.txt"): None}
    assert (tmp_path / "outside.txt").read_bytes() == b"not yours"


def test_the_command_runs_in_the_case_directory(log: EventLog, tmp_path: Path) -> None:
    (tmp_path / "work" / "sub").mkdir(parents=True)

    shown = run(log, tmp_path, case("import os; print(os.path.basename(os.getcwd()))", cwd="sub"))

    assert shown.outputs[(STDOUT, "")] == b"sub\n"


def test_the_frozen_input_is_the_standard_input(log: EventLog, tmp_path: Path) -> None:
    data = tmp_path / "in.txt"
    data.write_bytes(b"hello\n")

    shown = run(log, tmp_path, case("import sys; print(sys.stdin.read().upper(), end='')"), data)

    assert shown.outputs[(STDOUT, "")] == b"HELLO\n"


def test_time_and_the_operation_are_reported(log: EventLog, tmp_path: Path) -> None:
    shown = run(log, tmp_path, case("pass"))

    assert shown.duration > 0
    assert shown.operation_id.startswith("run_tool:")
    assert shown.peak_memory is None or shown.peak_memory > 0


def test_the_proxy_is_in_the_environment(log: EventLog, tmp_path: Path) -> None:
    shown = run(log, tmp_path, case("import os; print(os.environ['HTTP_PROXY'])"))

    assert shown.outputs[(STDOUT, "")].startswith(b"http://127.0.0.1:")  # type: ignore[union-attr]


def test_a_directory_outside_the_repository_is_not_decided(log: EventLog, tmp_path: Path) -> None:
    with pytest.raises(Undecided) as stop:
        run(log, tmp_path, case("pass", cwd="missing"))

    result = stop.value.result
    assert isinstance(result, Inconclusive)
    assert result.reason is InconclusiveReason.TOOL_FAILED
    assert "missing" in (result.detail or "")


def test_a_command_that_cannot_start_is_not_decided(log: EventLog, tmp_path: Path) -> None:
    spec = DifferentialCase("c", (str(tmp_path / "no-such-program"),))

    with pytest.raises(Undecided) as stop:
        run(log, tmp_path, spec)

    assert isinstance(stop.value.result, Inconclusive)
    assert "could not start" in (stop.value.result.detail or "")


def test_a_command_that_times_out_is_not_decided(log: EventLog, tmp_path: Path) -> None:
    (tmp_path / "work").mkdir()
    spec = case("import time; time.sleep(30)")

    with pytest.raises(Undecided) as stop:
        asyncio.run(
            run_case(tools(log, tmp_path, {"differential": 0.5}), spec, tmp_path / "work", None, {})
        )

    assert stop.value.result.reason is InconclusiveReason.TIMED_OUT  # type: ignore[union-attr]


def test_stdout_of_keeps_only_the_standard_output_channel() -> None:
    log = b"[out] one\n[err] two\n[out] three\n[out] \n"

    assert stdout_of(log) == b"one\nthree\n\n"


def test_stdout_of_does_not_take_a_line_that_only_mentions_the_prefix() -> None:
    assert stdout_of(b"[err] [out] x\n") == b""
