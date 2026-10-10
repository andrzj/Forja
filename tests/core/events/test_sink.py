import asyncio
import json
import subprocess
from pathlib import Path

from forja.core.events import LogEventSink
from forja.core.process import ProcessIdentity, ProcessRunner, creation_token, kill_leftover
from forja.core.states import Level
from tests.core.events.support import RUN, create_run, open_log
from tests.core.process.support import minimal_env, python, spec, wait_until_dead


def _records(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_bytes().splitlines()]


def test_a_process_run_is_recorded_as_intent_started_output_and_effect(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    with open_log(path) as log:
        create_run(log)
        sink = LogEventSink(log, Level.EXECUTION, RUN, "run_tool")
        result = asyncio.run(
            ProcessRunner(sink).run("op1", spec("print('hello')"), tmp_path / "op1.log")
        )

        assert log.state.open_operations == {}
        assert log.state.leftover_processes() == []

    kinds = [(r["type"], r["payload"].get("kind")) for r in _records(path)[1:]]  # type: ignore[attr-defined]
    assert kinds == [
        ("intent", None),
        ("progress", "process_started"),
        ("progress", "output"),
        ("effect", None),
    ]
    effect = _records(path)[-1]
    assert effect["payload"]["exit_code"] == 0  # type: ignore[index]
    assert effect["payload"]["outcome"] == result.outcome.value  # type: ignore[index]


def test_long_output_lines_are_cut_at_1_kib_on_a_character_boundary(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    with open_log(path) as log:
        create_run(log)
        sink = LogEventSink(log, Level.EXECUTION, RUN, "run_tool")
        sink.intent("op1", {"command": ["x"]})
        sink.progress("op1", "out", "short")
        sink.progress("op1", "out", "a" + "é" * 600)  # byte 1024 falls inside a character

    short, cut = (r["payload"] for r in _records(path)[-2:])
    assert (short["line"], short["truncated"]) == ("short", False)  # type: ignore[index]
    assert cut["truncated"] is True  # type: ignore[index]
    assert len(cut["line"].encode()) <= 1024  # type: ignore[index]


def test_an_interrupted_run_leaves_the_identity_needed_to_kill_the_leftover(
    tmp_path: Path,
) -> None:
    path = tmp_path / "events.jsonl"
    child = subprocess.Popen(python("import time; time.sleep(60)"), env=minimal_env())
    try:
        identity = ProcessIdentity(child.pid, creation_token(child.pid))
        with open_log(path) as log:
            create_run(log)
            sink = LogEventSink(log, Level.EXECUTION, RUN, "call_agent_cli")
            sink.intent("op1", {"command": ["agent"]})
            sink.started("op1", identity)
        # the tool "crashes" here: no effect was recorded

        with open_log(path) as resumed:
            leftovers = resumed.state.leftover_processes()
            assert leftovers == [identity]
            assert kill_leftover(leftovers[0]) is True
        assert wait_until_dead(child.pid)
    finally:
        child.kill()
        child.wait()
