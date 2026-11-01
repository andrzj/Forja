from pathlib import Path

from forja.core.process import Outcome, ProcessSpec
from tests.core.process.support import run_to_end, spec

MB = 2**20
HOLD = "b = bytearray({size} * 2**20); b[::4096] = b'x' * len(b[::4096]); "
CHILD = HOLD.format(size=200) + "import time; time.sleep(0.3)"


def test_a_process_that_holds_memory_reports_a_peak_at_least_that_big(tmp_path: Path) -> None:
    result, _ = run_to_end(spec(CHILD), tmp_path / "op.log")

    assert result.outcome is Outcome.EXITED
    assert result.peak_memory is not None
    assert 200 * MB <= result.peak_memory < 400 * MB


def test_the_peak_is_the_sum_held_at_once_by_the_whole_tree(tmp_path: Path) -> None:
    code = (
        HOLD.format(size=150)
        + "import subprocess, sys; subprocess.run([sys.executable, '-c', "
        + repr(CHILD)
        + "])"
    )

    result, _ = run_to_end(spec(code), tmp_path / "op.log")

    assert result.peak_memory is not None
    assert 350 * MB <= result.peak_memory < 600 * MB


def test_memory_held_one_after_another_is_not_summed(tmp_path: Path) -> None:
    code = (
        "import subprocess, sys; "
        f"subprocess.run([sys.executable, '-c', {CHILD!r}]); "
        f"subprocess.run([sys.executable, '-c', {CHILD!r}])"
    )

    result, _ = run_to_end(spec(code), tmp_path / "op.log")

    assert result.peak_memory is not None
    assert result.peak_memory < 350 * MB


def test_a_command_that_cannot_start_has_no_measure(tmp_path: Path) -> None:
    result, _ = run_to_end(
        ProcessSpec(command=[str(tmp_path / "does-not-exist")], cwd=tmp_path, env={}, timeout=5),
        tmp_path / "op.log",
    )

    assert result.outcome is Outcome.SPAWN_FAILED
    assert result.peak_memory is None
