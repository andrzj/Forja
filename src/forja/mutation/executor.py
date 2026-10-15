"""Run mutants: change one file at a time in a throwaway copy and see whether the tests notice.

Nothing here knows a language. The caller hands over each mutant as the bytes the file would
have, the tests that cover the changed line, and a function that runs those tests.
"""

import asyncio
import os
import shutil
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import ClassVar, Protocol

from forja.core.reports.models import MutantResult, MutantStatus, MutationReport

LEFT_OUT = (".git", ".venv", "venv", "node_modules", "__pycache__", ".mypy_cache", ".ruff_cache")
MIN_TIMEOUT = 10.0
TIMEOUT_FACTOR = 3.0


class TestVerdict(StrEnum):
    __test__ = False  # not a test class, whatever its name says to pytest

    PASSED = "passed"
    FAILED = "failed"  # a test failed or the code no longer loads: the change was noticed
    TIMED_OUT = "timed_out"


class TestsDidNotRun(Exception):
    """The tool could not run at all (not found, stopped): no verdict about any mutant."""

    __test__ = False


class TestRunner(Protocol):
    __test__: ClassVar[bool] = False

    async def __call__(
        self, root: Path, selectors: Sequence[str], timeout: float | None
    ) -> TestVerdict: ...


@dataclass(frozen=True)
class Mutant:
    file: str  # repository-relative POSIX path
    line: int
    change: str  # the tool's text for the change, e.g. "<= -> <"
    function: str | None
    mutated: bytes  # the whole file as the mutant has it
    tests: tuple[str, ...]  # what to run; empty means no test covers the line


class BaselineFailed(Exception):
    """The tests do not pass on the unchanged copy, so a failure would prove nothing."""


def _fresh_copy(source: Path, target: Path) -> None:
    shutil.copytree(source, target, ignore=shutil.ignore_patterns(*LEFT_OUT))


def _clean_bytecode(root: Path) -> None:
    for cache in root.rglob("__pycache__"):
        shutil.rmtree(cache, ignore_errors=True)


async def _judge(
    runner: TestRunner, root: Path, path: Path, original: bytes, mutant: Mutant, timeout: float
) -> MutantStatus:
    if not mutant.tests:
        return MutantStatus.UNCOVERED
    try:
        path.write_bytes(mutant.mutated)
        # a stale bytecode file of the same size and time could run the original code
        _clean_bytecode(root)
        verdict = await runner(root, mutant.tests, timeout)
    finally:
        path.write_bytes(original)
        _clean_bytecode(root)
    return {
        TestVerdict.PASSED: MutantStatus.SURVIVED,
        TestVerdict.FAILED: MutantStatus.KILLED,
        TestVerdict.TIMED_OUT: MutantStatus.TIMEOUT,
    }[verdict]


async def _work(
    queue: "asyncio.Queue[tuple[int, Mutant]]",
    results: dict[int, MutantStatus],
    runner: TestRunner,
    root: Path,
    timeout: float,
) -> None:
    while True:
        try:
            index, mutant = queue.get_nowait()
        except asyncio.QueueEmpty:
            return
        path = root / mutant.file
        results[index] = await _judge(runner, root, path, path.read_bytes(), mutant, timeout)


async def run_mutants(
    worktree: Path,
    scratch: Path,
    mutants: Sequence[Mutant],
    runner: TestRunner,
    *,
    workers: int | None = None,
    baseline_timeout: float | None = None,
) -> MutationReport:
    """Judge every mutant. ``scratch`` is an empty directory for the copies; the caller removes it.

    The baseline run (all selectors of all mutants, unchanged copy) must pass; its duration
    sets the timeout of each mutant at three times that, but never below ten seconds.
    """
    count = max(1, workers if workers is not None else min(4, os.cpu_count() or 1))
    roots = [scratch / f"worker-{n}" for n in range(count)]
    for root in roots:
        await asyncio.to_thread(_fresh_copy, worktree, root)
    selectors = tuple(sorted({s for m in mutants for s in m.tests}))
    loop = asyncio.get_running_loop()
    started = loop.time()
    if selectors and await runner(roots[0], selectors, baseline_timeout) is not TestVerdict.PASSED:
        raise BaselineFailed("the tests do not pass on the unchanged copy")
    timeout = max(MIN_TIMEOUT, TIMEOUT_FACTOR * (loop.time() - started))
    queue: asyncio.Queue[tuple[int, Mutant]] = asyncio.Queue()
    for item in enumerate(mutants):
        queue.put_nowait(item)
    results: dict[int, MutantStatus] = {}
    await asyncio.gather(*(_work(queue, results, runner, root, timeout) for root in roots))
    return MutationReport(
        tuple(
            MutantResult(m.file, m.line, m.change, results[i], m.function)
            for i, m in enumerate(mutants)
        )
    )
