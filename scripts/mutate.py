"""The mutation gate, as one command whose answer is the exit code.

    scripts/mutate.py              # the source files changed since HEAD (and new ones)
    scripts/mutate.py --all        # every source file
    scripts/mutate.py src/forja/checks/changes.py

It runs the engine (unclebob/mutator) the way the engine is meant to be run: the coverage report
decides which sites are run (a site no test reaches is reported as uncovered, not run), and the
snapshot the engine keeps in ``.metrics/mutate`` makes every run after the first differential (only
survivors and the functions whose text changed are run again; ``--fresh`` runs everything). What
the script adds is the choice of tests: only those that exercise the file, found from a coverage
run that records which test ran each line. A surviving mutant fails the run
unless ``mutation-suppressions.toml`` names it, with a reason a person approved. Nothing in the
source can switch the gate off: a comment that does is rejected by the scope gate.

Exit: 0 every mutant was killed or suppressed; 2 the tests fail before any mutation; 3 a mutant
survived; 4 the canary failed. It needs a POSIX shell, so on Windows run it inside WSL.
"""

import argparse
import ast
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import tomllib
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SUPPRESSIONS = ROOT / "mutation-suppressions.toml"
COVERAGE = ROOT / "target" / "coverage" / "python"
NL = chr(10)
LCOV = COVERAGE / "lcov.info"  # where the engine looks for the coverage of a Python project
OUTCOME = re.compile(
    r"^(KILLED|SURVIVED|UNCOVERED)\s+(?P<file>\S+?):(?P<line>\d+)\s+(?P<change>.+)$"
)
FAST = {"FORJA_FAST": "1"}
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
        env=FAST,
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
    out, records = [], lcov.split("end_of_record\n")
    for record in records:
        lines = record.splitlines()
        name = next((line[3:] for line in lines if line.startswith("SF:")), None)
        if name is None:
            continue
        path = Path(name) if Path(name).is_absolute() else ROOT / name
        hits: dict[int, int] = {}
        for line in lines:
            if line.startswith("DA:"):
                number, count = line[3:].split(",")[:2]
                hits[int(number)] = int(count)
        if path.is_file():
            for first, last in statement_spans(path.read_text(encoding="utf-8")):
                if hits.get(first, 0) > 0:
                    for number in range(first + 1, last + 1):
                        hits[number] = max(hits.get(number, 0), hits[first])
        kept = [line for line in lines if not line.startswith(("DA:", "LF:", "LH:"))]
        end = kept.index("end_of_record") if "end_of_record" in kept else len(kept)
        body = [f"DA:{number},{count}" for number, count in sorted(hits.items())]
        body += [f"LF:{len(hits)}", f"LH:{sum(1 for c in hits.values() if c > 0)}"]
        out.append(NL.join([*kept[:end], *body, "end_of_record"]) + NL)
    return "".join(out)


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


def function_at(source: Path, line: int) -> str:
    """The qualified name of the innermost function that holds ``line``."""
    best, span = "<module>", None

    def visit(node: ast.AST, prefix: str) -> None:
        nonlocal best, span
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
                name = f"{prefix}{child.name}"
                end = child.end_lineno or child.lineno
                inside = child.lineno <= line <= end and not isinstance(child, ast.ClassDef)
                if inside and (span is None or end - child.lineno <= span):
                    best, span = name, end - child.lineno
                visit(child, f"{name}.")
            else:
                visit(child, prefix)

    visit(ast.parse(source.read_text(encoding="utf-8")), "")
    return best


def mutate(
    file: str, tests: list[str], engine: Path, workers: int, *, fresh: bool = False
) -> tuple[int, list[str], list[str]]:
    skipped = " ".join(f"--deselect {name}" for name in settings().get("deselect", []))
    # --timeout: a mutant that loops forever fails its test in seconds, instead of the engine
    # waiting ten times the whole baseline for it
    base = f"{sys.executable} -m pytest -q -x -p no:cacheprovider -n0 --timeout={TEST_TIMEOUT}"
    command = f"{base} {skipped} {' '.join(tests)}"
    done = run(
        str(engine), "--use-existing-coverage", *(["--mutate-all"] if fresh else []),
        "--max-workers", str(workers), "--test-command", command, file, env=FAST,
    )  # fmt: skip
    survived, uncovered = [], []
    for text in done.stdout.splitlines():
        found = OUTCOME.match(text)
        if found and found[1] == "SURVIVED":
            survived.append(f"{found['file']}:{found['line']} {found['change']}")
        elif found and found[1] == "UNCOVERED":
            uncovered.append(f"{found['file']}:{found['line']} {found['change']}")
    return done.returncode, survived, uncovered


def canary(engine: Path) -> bool:
    """Prove the harness can tell a mutant from a failed command, before trusting any verdict.

    A tiny project is mutated twice with the same shape of command the gate uses: tests that
    check nothing must let the mutant survive, and tests that check the sum must kill it. A
    command that fails for its own reasons (a wrong path, a missing module) would "kill" both.
    """
    with tempfile.TemporaryDirectory(prefix="forja-canary-") as name:
        root = Path(name)
        (root / "src").mkdir()
        (root / "tests").mkdir()
        (root / "src" / "canary.py").write_text("def add(a, b):\n    return a + b\n", "utf-8")
        head = "from canary import add\n\n\ndef test_it():\n    assert "
        (root / "tests" / "test_loose.py").write_text(head + "add(1, 2) is not None\n", "utf-8")
        (root / "tests" / "test_tight.py").write_text(head + "add(1, 2) == 3\n", "utf-8")
        results = {}
        for kind in ("loose", "tight"):
            command = (
                f"{sys.executable} -m pytest -q -x -p no:cacheprovider -n0 -o pythonpath=src "
                f"tests/test_{kind}.py"
            )
            done = run(
                str(engine), "--no-coverage", "--mutate-all", "--test-command", command,
                "src/canary.py", cwd=root, env=FAST,
            )  # fmt: skip
            results[kind] = (done.returncode, done.stdout.count("SURVIVED"))
    return results["loose"][1] >= 1 and results["tight"] == (0, 0)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("files", nargs="*")
    parser.add_argument("--all", action="store_true")
    parser.add_argument(
        "--engine",
        default=os.environ.get("FORJA_MUTATOR", str(Path.home() / "mutator" / "mutator")),
    )
    parser.add_argument("--workers", type=int, default=os.cpu_count() or 1)
    parser.add_argument("--reuse-coverage", action="store_true")
    parser.add_argument("--skip-canary", action="store_true")
    parser.add_argument(
        "--fresh", action="store_true", help="run every mutant again, ignoring the snapshot"
    )
    args = parser.parse_args()
    files = args.files or (all_sources() if args.all else changed_sources())
    if not files:
        print("no source file changed: nothing to mutate")
        return 0
    started = time.monotonic()
    if not args.skip_canary and not canary(Path(args.engine)):
        print("the canary failed: the harness cannot tell a mutant from a broken command")
        return 4
    print(f"canary: {time.monotonic() - started:.0f}s")
    started = time.monotonic()
    tests_of = record_coverage(args.reuse_coverage)
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
        code, survived, uncovered = mutate(
            file, tests, Path(args.engine), args.workers, fresh=args.fresh
        )
        took = time.monotonic() - started
        print(f"[{number}/{len(files)}] {file}: {len(tests)} test file(s), {took:.0f}s", flush=True)
        if code == 2:
            print(f"{file}: the tests fail before any mutation")
            return 2
        for entry in survived:
            where, _, change = entry.partition(" ")
            path, _, line = where.rpartition(":")
            function = function_at(ROOT / path, int(line))
            muted = any(
                s["file"] == path and s["function"] == function and s["change"] == change
                for s in allowed
            )
            if not muted:
                print(f"SURVIVED {entry}  [{function}]")
                survivors += 1
        if uncovered:
            unreached += len(uncovered)
            print(f"{file}: {len(uncovered)} site(s) on lines no test runs (not run)")
    print(
        "mutation: "
        + ("all mutants killed or suppressed" if not survivors else f"{survivors} survived")
    )
    if unreached:
        print(f"{unreached} site(s) on lines no test runs: write a test, or the code is not needed")
    return 3 if survivors else 0


if __name__ == "__main__":
    sys.exit(main())
