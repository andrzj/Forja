import asyncio
import sys
from pathlib import Path

import pytest

from forja.core.process import Outcome, ProcessIdentity, ProcessRunner, ProcessSpec
from tests.core.process.support import (
    RecordingSink,
    minimal_env,
    python,
    run_to_end,
    spec,
    wait_until_dead,
)

SPAWN_SLEEPING_CHILD = (
    "import subprocess, sys, time\n"
    "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
    "print(child.pid, flush=True)\n"
)


def test_successful_run_reports_output_in_order_and_writes_the_raw_log(tmp_path: Path) -> None:
    log = tmp_path / "logs" / "op.log"
    code = "import sys; print('hello'); print('oops', file=sys.stderr)"

    result, sink = run_to_end(spec(code), log)

    assert result.outcome is Outcome.EXITED
    assert result.exit_code == 0
    assert sink.kinds()[0] == "intent"
    assert sink.kinds()[1] == "started"
    assert sink.kinds()[-1] == "effect"
    assert sink.lines("out") == ["hello"]
    assert sink.lines("err") == ["oops"]
    text = log.read_text()
    assert "[out] hello" in text
    assert "[err] oops" in text


def test_non_zero_exit_code_is_recorded_not_raised(tmp_path: Path) -> None:
    result, sink = run_to_end(spec("raise SystemExit(7)"), tmp_path / "op.log")

    assert result.outcome is Outcome.EXITED
    assert result.exit_code == 7
    assert sink.of("effect")["exit_code"] == 7  # type: ignore[index]


def test_intent_lists_environment_names_but_never_values(tmp_path: Path) -> None:
    _, sink = run_to_end(spec("pass", API_KEY="s3cr3t-value"), tmp_path / "op.log")

    intent = sink.of("intent")
    assert "API_KEY" in intent["env_names"]  # type: ignore[index]
    assert "s3cr3t-value" not in str(intent)


def test_child_gets_only_the_declared_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FORJA_PARENT_ONLY", "leaked")
    code = "import os; print(os.environ.get('FORJA_PARENT_ONLY'), os.environ.get('DECLARED'))"

    _, sink = run_to_end(spec(code, DECLARED="yes"), tmp_path / "op.log")

    assert sink.lines("out") == ["None yes"]


def test_very_long_lines_and_invalid_utf8_are_handled(tmp_path: Path) -> None:
    code = (
        "import sys; print('x' * 300000); sys.stdout.flush(); "
        "sys.stdout.buffer.write(b'ok\\xff\\n')"
    )

    _, sink = run_to_end(spec(code), tmp_path / "op.log")

    lines = sink.lines("out")
    assert len(lines[0]) == 300000
    assert lines[1] == "ok�"


def test_spawn_failure_records_intent_and_effect_only(tmp_path: Path) -> None:
    missing = ProcessSpec(["forja-no-such-binary"], tmp_path, minimal_env(), timeout=5)

    result, sink = run_to_end(missing, tmp_path / "op.log")

    assert result.outcome is Outcome.SPAWN_FAILED
    assert result.exit_code is None
    assert sink.kinds() == ["intent", "effect"]


def test_timeout_kills_the_process_and_reports_it(tmp_path: Path) -> None:
    result, sink = run_to_end(
        spec("import time; time.sleep(60)", timeout=0.5, grace=0.5), tmp_path / "op.log"
    )

    assert result.outcome is Outcome.TIMED_OUT
    assert result.duration < 10
    identity = sink.of("started")
    assert isinstance(identity, ProcessIdentity)
    assert wait_until_dead(identity.pid)


def test_timeout_kills_descendants_too(tmp_path: Path) -> None:
    code = SPAWN_SLEEPING_CHILD + "import time; time.sleep(60)"

    result, sink = run_to_end(spec(code, timeout=1.5, grace=0.5), tmp_path / "op.log")

    assert result.outcome is Outcome.TIMED_OUT
    assert wait_until_dead(int(sink.lines("out")[0]))


def test_descendants_left_behind_after_a_normal_exit_are_killed(tmp_path: Path) -> None:
    result, sink = run_to_end(spec(SPAWN_SLEEPING_CHILD, timeout=20), tmp_path / "op.log")

    assert result.outcome is Outcome.EXITED
    assert result.duration < 10
    assert wait_until_dead(int(sink.lines("out")[0]))


GRACEFUL_CHILD = (
    "import signal, sys, time\n"
    "def bye(*_):\n"
    "    print('graceful', flush=True); sys.exit(0)\n"
    "signal.signal(getattr(signal, 'SIGBREAK', signal.SIGTERM), bye)\n"
    "print('ready', flush=True)\n"
    "time.sleep(60)\n"
)


@pytest.mark.skipif(sys.platform == "win32", reason="Ctrl+Break needs a console attached")
def test_timeout_asks_politely_before_killing(tmp_path: Path) -> None:
    result, sink = run_to_end(spec(GRACEFUL_CHILD, timeout=1.0, grace=10), tmp_path / "op.log")

    assert result.outcome is Outcome.TIMED_OUT
    assert "graceful" in sink.lines("out")
    assert result.duration < 8


def test_a_process_that_ignores_the_polite_request_is_killed_after_the_grace_period(
    tmp_path: Path,
) -> None:
    stubborn = (
        "import signal, time\n"
        "signal.signal(getattr(signal, 'SIGBREAK', signal.SIGTERM), signal.SIG_IGN)\n"
        "time.sleep(60)\n"
    )

    result, _ = run_to_end(spec(stubborn, timeout=0.5, grace=0.5), tmp_path / "op.log")

    assert result.outcome is Outcome.TIMED_OUT
    assert result.duration < 10


def test_cancelling_the_task_stops_the_tree_records_the_effect_and_reraises(
    tmp_path: Path,
) -> None:
    sink = RecordingSink()
    code = SPAWN_SLEEPING_CHILD + "import time; time.sleep(60)"

    async def scenario() -> None:
        runner = ProcessRunner(sink)
        task = asyncio.create_task(runner.run("op-1", spec(code), tmp_path / "op.log"))
        while "started" not in sink.kinds() or not sink.lines("out"):
            await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(scenario())

    assert sink.of("effect")["outcome"] == "cancelled"  # type: ignore[index]
    identity = sink.of("started")
    assert isinstance(identity, ProcessIdentity)
    assert wait_until_dead(identity.pid)
    assert wait_until_dead(int(sink.lines("out")[0]))


def test_command_is_never_run_through_a_shell(tmp_path: Path) -> None:
    code = "import sys; print(sys.argv[1:])"
    process_spec = ProcessSpec(
        [*python(code), "a b", "&& echo injected"], tmp_path, minimal_env(), timeout=20
    )

    _, sink = run_to_end(process_spec, tmp_path / "op.log")

    assert sink.lines("out") == ["['a b', '&& echo injected']"]
