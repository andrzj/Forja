"""Gate 11: one run of one differential case, and what it left to compare.

The command is the case's own, a list of arguments the program gets as they are. It runs inside the
network trap, like the E2E, and the files it was declared to write are read after it ends into
memory, so what is compared never stays in a place the implementer can edit. A non-zero exit code is
a value to compare, not a failure of the tool; a command that did not run to the end is.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from forja.checks.base import Undecided
from forja.checks.e2e_plan import e2e_environment
from forja.checks.network_trap import NetworkTrap
from forja.checks.readme_gate import inside
from forja.checks.tooling import Tools
from forja.core.adapters import CommandPlan
from forja.core.gates import Inconclusive, InconclusiveReason
from forja.core.policy.differential import (
    EXIT_CODE,
    FILE,
    STDOUT,
    DifferentialCase,
    DifferentialOutput,
)

CHECK = "differential"
_OUT = b"[out] "


@dataclass(frozen=True)
class CaseRun:
    """What a run showed. ``outputs`` holds, by (kind, path), the bytes of each declared output:
    the exit code as its decimal text, a file that was not there as ``None``. ``duration`` is in
    seconds; ``peak_memory`` is in bytes, ``None`` where the platform does not measure it."""

    outputs: dict[tuple[str, str], bytes | None]
    duration: float
    peak_memory: int | None
    operation_id: str


def stdout_of(log: bytes) -> bytes:
    """The standard output in the raw log, which interleaves both channels one prefixed line each.

    Line ends come out as ``\\n`` and the last line always has one: the runner splits lines.
    """
    return b"".join(line[len(_OUT) :] for line in log.splitlines(keepends=True) if _OUT in line[:6])


async def run_case(
    tools: Tools,
    case: DifferentialCase,
    worktree: Path,
    stdin: Path | None,
    host_env: Mapping[str, str],
) -> CaseRun:
    """Run ``case`` once in ``worktree``; ``stdin`` is the frozen copy of the case's input.

    Raises ``Undecided`` when the command did not run to the end, or its directory is not there.
    """
    cwd = inside(worktree, case.cwd) if case.cwd else worktree
    if cwd is None or not cwd.is_dir():
        raise Undecided(
            Inconclusive(
                reason=InconclusiveReason.TOOL_FAILED,
                detail=f"{CHECK}: case {case.name}: {case.cwd} is not a directory here",
            )
        )
    async with NetworkTrap() as trap:
        plan = CommandPlan(
            case.command,
            cwd,
            env_set=e2e_environment(trap.url, host_env),
            stdin_file=stdin,
        )
        execution = await tools.run(CHECK, plan)
    if not execution.finished:
        raise Undecided(execution.inconclusive(f"{CHECK}: case {case.name}"))
    result = execution.result
    return CaseRun(
        {
            (output.kind, output.path): _read(output, worktree, result.exit_code, result.log_path)
            for output in case.outputs
        },
        result.duration,
        result.peak_memory,
        execution.operation_id,
    )


def _read(
    output: DifferentialOutput, worktree: Path, exit_code: int | None, log_path: Path
) -> bytes | None:
    if output.kind == EXIT_CODE:
        return str(exit_code).encode()
    if output.kind == STDOUT:
        try:
            return stdout_of(log_path.read_bytes())
        except OSError:
            return None
    assert output.kind == FILE
    found = inside(worktree, output.path)
    try:
        return found.read_bytes() if found is not None and found.is_file() else None
    except OSError:
        return None
