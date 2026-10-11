"""Stand-ins for ruff, python -m compileall/pytest and lizard that read markers from the files.

They print what the real tools print (the shapes the adapter's parsers were written against), so
the checks can be tested in milliseconds. Markers, one per line, in comments:

    # LINT:F401        a lint violation with that code on this line
    # SYNTAX           a syntax error (lint reports it, format and compileall refuse the file)
    # UNFORMATTED      the formatter would change this file
    # NOCOMPILE        compileall cannot compile this file
    # BREAKS           (in a non-test file) every test fails
    # FAILS            the test defined on this line fails (a test is a ``def test_*`` line)
    # FLAKY            the test passes the first time it runs in a directory and fails after

Usage: ``fake_tools.py ruff|python|lizard ARGS...`` with the arguments the adapter plans.
"""

import hashlib
import sys
import tempfile
from pathlib import Path


def python_files(targets: list[str]) -> list[Path]:
    found: list[Path] = []
    for target in targets or ["."]:
        path = Path(target)
        if path.is_dir():
            found += sorted(p for p in path.rglob("*.py") if ".git" not in p.parts)
        elif path.is_file():
            found.append(path)
    return found


def shown(path: Path) -> str:
    return path.as_posix().removeprefix("./")


def targets_of(args: list[str]) -> list[str]:
    return (
        args[args.index("--") + 1 :] if "--" in args else [a for a in args if not a.startswith("-")]
    )


def ruff(args: list[str]) -> int:
    if "--version" in args:
        print("ruff 0.0.0-fake")
        return 0
    files = python_files(targets_of(args[1:]))
    if args[0] == "format":
        return ruff_format(files, "--check" in args)
    return ruff_check(files, "--exit-zero" in args)


def ruff_check(files: list[Path], exit_zero: bool) -> int:
    found = 0
    for path in files:
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if "# SYNTAX" in line:
                print(f"{shown(path)}:{number}:1: invalid-syntax: fake syntax error")
                found += 1
            elif "# LINT:" in line:
                code = line.split("# LINT:", 1)[1].split()[0]
                print(f"{shown(path)}:{number}:1: {code} fake violation")
                found += 1
    print(f"Found {found} errors." if found else "All checks passed!")
    return 1 if found and not exit_zero else 0


def ruff_format(files: list[Path], check: bool) -> int:
    changed = 0
    for path in files:
        text = path.read_text(encoding="utf-8")
        if "# SYNTAX" in text:
            print("invalid-syntax: fake syntax error")
            print(f" --> {shown(path)}:1:1")
            changed += 1
        elif "# UNFORMATTED" in text:
            print("unformatted: File would be reformatted")
            print(f" --> {shown(path)}:1:1")
            changed += 1
    if changed and check:
        return 2 if any("# SYNTAX" in p.read_text(encoding="utf-8") for p in files) else 1
    return 0


def python(args: list[str]) -> int:
    if "--version" in args and "pytest" not in args:
        print("Python 0.0.0-fake")
        return 0
    if args[:2] == ["-m", "pytest"]:
        return pytest(args[2:])
    if args[:2] == ["-m", "compileall"]:
        failed = 0
        for path in python_files(targets_of(args[2:])):
            if "# NOCOMPILE" in path.read_text(encoding="utf-8") or "# SYNTAX" in path.read_text(
                encoding="utf-8"
            ):
                print(f"*** Error compiling '{shown(path)}'...")
                failed += 1
        return 1 if failed else 0
    return 2


def pytest(args: list[str]) -> int:
    if "--version" in args:
        print("pytest 0.0.0-fake")
        return 0
    wanted = args[args.index("--") + 1 :] if "--" in args else []
    tests = [p for p in python_files(wanted) if p.name.startswith("test_")]
    state = Path(tempfile.gettempdir()) / (
        "fake-flaky-" + hashlib.sha1(str(Path.cwd()).encode()).hexdigest()[:12]
    )
    seen = state.exists()
    breaks = any(
        "# BREAKS" in p.read_text(encoding="utf-8")
        for p in python_files(["."])
        if not p.name.startswith("test_")
    )
    results: list[tuple[str, str]] = []
    for path in tests:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("def test_"):
                name = line[4 : line.index("(")]
                fails = breaks or "# FAILS" in line or ("# FLAKY" in line and seen)
                results.append((f"{shown(path)}::{name}", "FAILED" if fails else "PASSED"))
    if "# FLAKY" in "".join(p.read_text(encoding="utf-8") for p in tests):
        state.write_text("seen")
    if not results:
        print("no tests ran in 0.01s")
        return 5
    for test_id, outcome in results:
        print(f"{outcome} {test_id}" + (" - assert False" if outcome == "FAILED" else ""))
    return 1 if any(o == "FAILED" for _, o in results) else 0


def lizard(args: list[str]) -> int:
    for path in python_files(targets_of(args)):
        lines = path.read_text(encoding="utf-8").splitlines()
        starts = [i for i, line in enumerate(lines) if line.startswith("def ")]
        for index, start in enumerate(starts):
            end = (starts[index + 1] if index + 1 < len(starts) else len(lines)) - 1
            name = lines[start][4 : lines[start].index("(")]
            body = lines[start + 1 : end + 1]
            ccn = 1 + sum(1 for line in body if line.strip().startswith(("if ", "elif ")))
            where = f"{name}@{start + 1}-{end + 1}@{shown(path)}"
            print(
                f'3,{ccn},9,1,{end - start + 1},"{where}","{shown(path)}",'
                f'"{name}","{name}( )",{start + 1},{end + 1}'
            )
    return 0


if __name__ == "__main__":
    tool, *rest = sys.argv[1:]
    sys.exit({"ruff": ruff, "python": python, "lizard": lizard}[tool](rest))
