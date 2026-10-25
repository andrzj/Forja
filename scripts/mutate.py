"""The mutation gate, as one command whose answer is the exit code.

    scripts/mutate.py              # the source files changed since HEAD (and new ones)
    scripts/mutate.py --all        # every source file
    scripts/mutate.py src/forja/checks/changes.py

It runs the Forja's own mutator (``forja.mutation``, the rules of unclebob/mutator on tree-sitter,
ADR 0021) on the Forja's own source, the way the mutator runs on any project: the coverage report
decides which sites are run (a site no test reaches is reported as uncovered, not run), each mutant
is judged by the test command, and a failing or timed-out run kills it. The choice of tests is the
script's: only those that exercise the file, found from a coverage run that records which test ran
each line. A surviving mutant fails the run unless ``mutation-suppressions.toml`` names it, with a
reason a person approved. Nothing in the source can switch the gate off: a comment that does is
rejected by the scope gate.

Exit: 0 every mutant was killed or suppressed; 2 the tests fail before any mutation; 3 a mutant
survived; 4 the canary failed. It runs wherever Python runs, Windows included.
"""

import argparse
import ast
import asyncio
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import tomllib
from collections import defaultdict
from pathlib import Path

from forja.core.reports.models import MutantStatus, MutationReport
from forja.mutation import apply_site, discover
from forja.mutation.executor import (
    BaselineFailed,
    Mutant,
    TestsDidNotRun,
    TestVerdict,
    run_mutants,
)

ROOT = Path(__file__).resolve().parent.parent
SUPPRESSIONS = ROOT / "mutation-suppressions.toml"
COVERAGE = ROOT / "target" / "coverage" / "python"
NL = chr(10)
LCOV = COVERAGE / "lcov.info"  # where the engine looks for the coverage of a Python project
# The integration tests run too: without them the code they alone reach (the call to the agent CLI,
# the way back) counts as untested. Each file only runs the test files that reach it.
TESTS_ENV: dict[str, str] = {}
TEST_TIMEOUT = 30  # seconds for one test; the slowest of the project takes a few


def run(
    *command: str, env: dict[str, str] | None = None, cwd: Path = ROOT
) -> subprocess.CompletedProcess[str]:
    merged = {**os.environ, **(env or {})}
    return subprocess.run(command, cwd=cwd, env=merged, capture_output=True, text=True)


def changed_sources() -> list[str]:
    tracked = run("git", "diff", "--name-only", "HEAD", "--", "src").stdout.split()
    fresh = run("git", "ls-files", "--others", "--exclude-standard", "--", "src").stdout.split()
    return sorted(p for p in {*tracked, *fresh} if p.endswith(".py") and (ROOT / p).is_file())


def all_sources() -> list[str]:
    found = (p.relative_to(ROOT).as_posix() for p in (ROOT / "src").rglob("*.py"))
    return sorted(p for p in found if not p.endswith("__init__.py"))


def settings() -> dict[str, list[str]]:
    """``[tool.forja.mutation]`` of pyproject.toml: tests that cannot run where the gate runs."""
    document = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    found: dict[str, list[str]] = document.get("tool", {}).get("forja", {}).get("mutation", {})
    return found


def deselected() -> list[str]:
    return [arg for name in settings().get("deselect", []) for arg in ("--deselect", name)]


def record_coverage(reuse: bool) -> dict[str, list[str]]:
    """Which test files ran each source file, from one run of the fast tests."""
    COVERAGE.mkdir(parents=True, exist_ok=True)
    data, report = COVERAGE / ".coverage", COVERAGE / "contexts.json"
    if not (reuse and report.exists() and LCOV.exists()):
        measure_coverage(data, report)
    files = json.loads(report.read_text(encoding="utf-8"))["files"]
    tests_of: dict[str, set[str]] = defaultdict(set)
    for name, info in files.items():
        for contexts in info.get("contexts", {}).values():
            for context in contexts:
                module = test_file(context)
                if module:
                    tests_of[Path(name).as_posix()].add(module)
    return {name: ordered(name, tests) for name, tests in tests_of.items()}


def measure_coverage(data: Path, report: Path) -> None:
    data.unlink(missing_ok=True)
    tested = run(
        sys.executable, "-m", "coverage", "run", f"--data-file={data}", "-m", "pytest", "-q",
        "-p", "no:cacheprovider", "--no-header", "-n0", "-m", "not slow", *deselected(), "tests",
        env=TESTS_ENV,
    )  # fmt: skip
    if tested.returncode != 0:
        print(tested.stdout[-3000:], file=sys.stderr)
        raise SystemExit(2)
    for kind, target in (("json", report), ("lcov", LCOV)):
        extra = ["--show-contexts"] if kind == "json" else []
        exported = run(
            sys.executable, "-m", "coverage", kind, f"--data-file={data}", *extra, "-o", str(target)
        )  # fmt: skip
        if exported.returncode != 0:
            print(exported.stderr, file=sys.stderr)
            raise SystemExit(2)
    LCOV.write_text(widen(LCOV.read_text(encoding="utf-8")), encoding="utf-8")


def statement_spans(source: str) -> list[tuple[int, int]]:
    """First and last line of each statement; of a compound one, only its header."""
    spans = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.stmt):
            continue
        body = getattr(node, "body", None)
        if body and isinstance(body, list) and isinstance(body[0], ast.stmt):
            header_end = max(node.lineno, body[0].lineno - 1)
            spans.append((node.lineno, header_end))
        else:
            spans.append((node.lineno, node.end_lineno or node.lineno))
    return spans


def widen(lcov: str) -> str:
    """Make a statement that spans several lines count as covered on all of them.

    ``coverage`` records the first line of a statement, so a mutation on the second line of a
    call or of a condition would be called uncovered although the statement runs. A statement is
    reached or it is not: the lines after the first take the hits of the first.
    """
    out = []
    for record in lcov.split("end_of_record\n"):
        lines = record.splitlines()
        name = next((line[3:] for line in lines if line.startswith("SF:")), None)
        if name is None:
            continue
        path = Path(name) if Path(name).is_absolute() else ROOT / name
        hits = line_hits(lines)
        if path.is_file():
            spread_hits(hits, statement_spans(path.read_text(encoding="utf-8")))
        out.append(render_record(lines, hits))
    return "".join(out)


def line_hits(lines: list[str]) -> dict[int, int]:
    hits: dict[int, int] = {}
    for line in lines:
        if line.startswith("DA:"):
            number, count = line[3:].split(",")[:2]
            hits[int(number)] = int(count)
    return hits


def spread_hits(hits: dict[int, int], spans: list[tuple[int, int]]) -> None:
    for first, last in spans:
        if hits.get(first, 0) > 0:
            for number in range(first + 1, last + 1):
                hits[number] = max(hits.get(number, 0), hits[first])


def render_record(lines: list[str], hits: dict[int, int]) -> str:
    kept = [line for line in lines if not line.startswith(("DA:", "LF:", "LH:"))]
    end = kept.index("end_of_record") if "end_of_record" in kept else len(kept)
    body = [f"DA:{number},{count}" for number, count in sorted(hits.items())]
    body += [f"LF:{len(hits)}", f"LH:{sum(1 for c in hits.values() if c > 0)}"]
    return NL.join([*kept[:end], *body, "end_of_record"]) + NL


def ordered(source: str, tests: set[str]) -> list[str]:
    """Tests named for the module first: they usually kill a mutant, so ``-x`` stops early."""
    stem = Path(source).stem
    return sorted(tests, key=lambda test: (stem not in Path(test).stem, test))


def test_file(context: str) -> str | None:
    """The test file of a coverage context (``tests.pkg.test_mod.Class.test_x``), if any."""
    parts = [part for part in context.split("|")[0].split(".") if part]
    while parts:
        candidate = Path(*parts).with_suffix(".py")
        if (ROOT / candidate).is_file():
            return candidate.as_posix()
        parts.pop()
    return None


def suppressions() -> list[dict[str, str]]:
    if not SUPPRESSIONS.exists():
        return []
    entries: list[dict[str, str]] = tomllib.loads(SUPPRESSIONS.read_text(encoding="utf-8")).get(
        "suppress", []
    )
    for entry in entries:
        if not all(entry.get(key) for key in ("file", "function", "change", "reason")):
            raise SystemExit(
                f"{SUPPRESSIONS.name}: every entry needs file, function, change, reason"
            )
    return entries


def covered_lines() -> dict[str, frozenset[int]]:
    """The lines a test runs, by source file, from the coverage report of the last run."""
    found: dict[str, frozenset[int]] = {}
    for record in LCOV.read_text(encoding="utf-8").split("end_of_record" + NL):
        lines = record.splitlines()
        name = next((line[3:] for line in lines if line.startswith("SF:")), None)
        if name is None:
            continue
        path = Path(name) if Path(name).is_absolute() else ROOT / name
        try:
            key = path.resolve().relative_to(ROOT).as_posix()
        except ValueError:
            continue
        found[key] = frozenset(number for number, count in line_hits(lines).items() if count > 0)
    return found


def mutants_of(file: str, root: Path, covered: frozenset[int]) -> list[Mutant]:
    source = (root / file).read_text(encoding="utf-8")
    return [
        Mutant(
            file, site.line, site.description, site.function,
            apply_site(source, site).encode("utf-8"), site.line in covered,
        )
        for site in discover(source, file)
    ]  # fmt: skip


def stop_tree(pid: int) -> None:
    """End a process and what it started: a mutant that loops must not leave workers behind."""
    if sys.platform == "win32":
        run("taskkill", "/F", "/T", "/PID", str(pid))
    else:
        os.killpg(pid, signal.SIGKILL)


class PytestRunner:
    """Runs the chosen test files in a copy of the project, as the executor asks."""

    __test__ = False

    def __init__(self, tests: list[str], deselect: list[str]) -> None:
        self.tests, self.deselect = tests, deselect

    async def __call__(self, root: Path, timeout: float | None) -> TestVerdict:
        # --timeout: a mutant that loops forever fails its test in seconds, instead of the
        # executor waiting ten times the whole baseline for it
        command = [
            sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", "-n0",
            f"--timeout={TEST_TIMEOUT}", *self.deselect, *self.tests,
        ]  # fmt: skip
        # the copy's own source must be the one imported, not the installed project's
        env = {
            **os.environ,
            **TESTS_ENV,
            "PYTHONPATH": str(root / "src"),
            "PYTHONDONTWRITEBYTECODE": "1",
        }
        process = await asyncio.create_subprocess_exec(
            *command, cwd=root, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=sys.platform != "win32",
        )  # fmt: skip
        try:
            code = await asyncio.wait_for(process.wait(), timeout)
        except TimeoutError:
            stop_tree(process.pid)
            await process.wait()
            return TestVerdict.TIMED_OUT
        if code == 0:
            return TestVerdict.PASSED
        if code in (1, 2):  # a test failed, or the changed code no longer loads
            return TestVerdict.FAILED
        raise TestsDidNotRun(f"pytest exited with {code}")


def judge(mutants: list[Mutant], runner: PytestRunner, workers: int) -> MutationReport:
    with tempfile.TemporaryDirectory(prefix="forja-mutants-", ignore_cleanup_errors=True) as copies:
        return asyncio.run(run_mutants(ROOT, Path(copies), mutants, runner, workers=workers))


def canary() -> bool:
    """Prove the harness can tell a mutant from a failed command, before trusting any verdict.

    A tiny project is mutated twice with the same runner the gate uses: tests that check nothing
    must let the mutant survive, and tests that check the sum must kill it. A command that fails
    for its own reasons (a wrong path, a missing module) would "kill" both.
    """
    with tempfile.TemporaryDirectory(prefix="forja-canary-") as name:
        root = Path(name) / "project"
        (root / "src").mkdir(parents=True)
        (root / "tests").mkdir()
        (root / "src" / "canary.py").write_text("def add(a, b):\n    return a + b\n", "utf-8")
        head = "from canary import add\n\n\ndef test_it():\n    assert "
        (root / "tests" / "test_loose.py").write_text(head + "add(1, 2) is not None\n", "utf-8")
        (root / "tests" / "test_tight.py").write_text(head + "add(1, 2) == 3\n", "utf-8")
        mutants = mutants_of("src/canary.py", root, frozenset({2}))
        survivors = {}
        for kind in ("loose", "tight"):
            runner = PytestRunner([f"tests/test_{kind}.py"], [])
            with tempfile.TemporaryDirectory(prefix="forja-canary-copies-") as copies:
                report = asyncio.run(run_mutants(root, Path(copies), mutants, runner, workers=1))
            survivors[kind] = len(report.with_status(MutantStatus.SURVIVED))
    return bool(mutants) and survivors["loose"] >= 1 and survivors["tight"] == 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("files", nargs="*")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--workers", type=int, default=min(8, os.cpu_count() or 1))
    parser.add_argument("--reuse-coverage", action="store_true")
    parser.add_argument("--skip-canary", action="store_true")
    return parser.parse_args()


def report_survivors(report: MutationReport, allowed: list[dict[str, str]]) -> int:
    """Print the survivors no suppression names; return how many there were."""
    count = 0
    for mutant in report.with_status(MutantStatus.SURVIVED):
        muted = any(
            s["file"] == mutant.file
            and s["function"] == mutant.function
            and s["change"] == mutant.change
            for s in allowed
        )
        if not muted:
            print(f"SURVIVED {mutant.file}:{mutant.line} {mutant.change}  [{mutant.function}]")
            count += 1
    return count


def main() -> int:
    args = parse_args()
    files = args.files or (all_sources() if args.all else changed_sources())
    if not files:
        print("no source file changed: nothing to mutate")
        return 0
    started = time.monotonic()
    if not args.skip_canary and not canary():
        print("the canary failed: the harness cannot tell a mutant from a broken command")
        return 4
    print(f"canary: {time.monotonic() - started:.0f}s")
    started = time.monotonic()
    tests_of = record_coverage(args.reuse_coverage)
    covered = covered_lines()
    print(f"coverage by test: {time.monotonic() - started:.0f}s")
    allowed = suppressions()
    survivors, unreached = 0, 0
    for number, file in enumerate(files, start=1):
        tests = tests_of.get(file)
        if not tests:
            print(f"{file}: no test runs it, so no mutant can be judged")
            survivors += 1
            continue
        started = time.monotonic()
        mutants = mutants_of(file, ROOT, covered.get(file, frozenset()))
        try:
            report = judge(mutants, PytestRunner(tests, deselected()), args.workers)
        except (BaselineFailed, TestsDidNotRun) as error:
            print(f"{file}: the tests fail before any mutation ({error})")
            return 2
        took = time.monotonic() - started
        print(f"[{number}/{len(files)}] {file}: {len(tests)} test file(s), {took:.0f}s", flush=True)
        survivors += report_survivors(report, allowed)
        missed = len(report.with_status(MutantStatus.UNCOVERED))
        if missed:
            unreached += missed
            print(f"{file}: {missed} site(s) on lines no test runs (not run)")
    print(
        "mutation: "
        + ("all mutants killed or suppressed" if not survivors else f"{survivors} survived")
    )
    if unreached:
        print(f"{unreached} site(s) on lines no test runs: write a test, or the code is not needed")
    return 3 if survivors else 0


if __name__ == "__main__":
    sys.exit(main())
