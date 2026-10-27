"""Gate 11: what the base showed for each case, measured once and kept outside the worktree.

Each case runs twice on the base. If the two runs differ by the case's own rules the case is not
deterministic and is put in quarantine: it stays as evidence and never rejects an attempt. The
outputs of the first run, the times and the memory peaks of both are written under ``directory``
(the run's data, not the worktree) so that every attempt compares with the same base.
"""

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from forja.checks.differential_compare import compare_output, describe
from forja.checks.differential_inputs import freeze_inputs
from forja.checks.differential_run import run_case
from forja.checks.tooling import Tools
from forja.core.atomic import atomic_write_bytes
from forja.core.policy.differential import DifferentialCase

INDEX = "index.json"
OUTPUTS = "outputs"
INPUTS = "inputs"
RUNS_ON_THE_BASE = 2


@dataclass(frozen=True)
class BaseCase:
    """``outputs`` are those of the first run, by (kind, path). ``durations`` and ``memories``
    are those of both runs (a run without a memory measure adds none). ``unstable`` names the
    outputs on which the two runs differed."""

    outputs: dict[tuple[str, str], bytes | None]
    durations: tuple[float, ...]
    memories: tuple[int, ...] = ()
    unstable: tuple[str, ...] = ()

    @property
    def quarantined(self) -> bool:
        return bool(self.unstable)


@dataclass(frozen=True)
class DifferentialBase:
    cases: dict[str, BaseCase] = field(default_factory=dict)
    inputs: dict[str, Path] = field(default_factory=dict)  # frozen stdin, by case name


async def measure_base(
    tools: Tools,
    cases: Iterable[DifferentialCase],
    worktree: Path,
    directory: Path,
    host_env: Mapping[str, str],
) -> DifferentialBase:
    """Run every case twice on ``worktree`` (the base) and write the result to ``directory``.

    Raises ``MissingInput`` for an input the base does not have and ``Undecided`` for a run that
    could not be made; nothing is written then.
    """
    cases = tuple(cases)
    inputs = freeze_inputs(cases, worktree, directory / INPUTS)
    found: dict[str, BaseCase] = {}
    for case in cases:
        runs = [
            await run_case(tools, case, worktree, inputs.get(case.name), host_env)
            for _ in range(RUNS_ON_THE_BASE)
        ]
        first, second = runs
        found[case.name] = BaseCase(
            first.outputs,
            tuple(run.duration for run in runs),
            tuple(run.peak_memory for run in runs if run.peak_memory is not None),
            tuple(
                describe(output)
                for output in case.outputs
                if compare_output(
                    output,
                    first.outputs[(output.kind, output.path)],
                    second.outputs[(output.kind, output.path)],
                )
                is not None
            ),
        )
    base = DifferentialBase(found, inputs)
    save(base, directory)
    return base


def save(base: DifferentialBase, directory: Path) -> None:
    """Write the outputs first and the index last: a directory without an index is not a base."""
    index: dict[str, Any] = {}
    for name, case in base.cases.items():
        listed = []
        for position, ((kind, path), content) in enumerate(case.outputs.items()):
            stored = None
            if content is not None:
                stored = f"{name}.{position}"
                atomic_write_bytes(directory / OUTPUTS / stored, content)
            listed.append({"kind": kind, "path": path, "file": stored})
        index[name] = {
            "outputs": listed,
            "durations": list(case.durations),
            "memories": list(case.memories),
            "unstable": list(case.unstable),
        }
    atomic_write_bytes(directory / INDEX, json.dumps(index, sort_keys=True).encode("utf-8"))


def load(directory: Path, cases: Iterable[DifferentialCase]) -> DifferentialBase | None:
    """The base kept in ``directory`` for exactly these cases; ``None`` when there is none, it is
    unreadable, or it was made for other cases."""
    cases = tuple(cases)
    names = {case.name for case in cases}
    try:
        index = json.loads((directory / INDEX).read_text(encoding="utf-8"))
        if set(index) != names:
            return None
        found = {name: _case_of(directory, entry) for name, entry in index.items()}
    except (OSError, ValueError, KeyError, TypeError):
        return None
    inputs = {case.name: directory / INPUTS / f"{case.name}.stdin" for case in cases if case.stdin}
    if not all(path.is_file() for path in inputs.values()):
        return None
    return DifferentialBase(found, inputs)


def _case_of(directory: Path, entry: Mapping[str, Any]) -> BaseCase:
    outputs: dict[tuple[str, str], bytes | None] = {}
    for item in entry["outputs"]:
        stored = item["file"]
        outputs[(str(item["kind"]), str(item["path"]))] = (
            None if stored is None else (directory / OUTPUTS / str(stored)).read_bytes()
        )
    return BaseCase(
        outputs,
        tuple(float(x) for x in entry["durations"]),
        tuple(int(x) for x in entry["memories"]),
        tuple(str(x) for x in entry["unstable"]),
    )
