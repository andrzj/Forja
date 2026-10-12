"""Check the planted-defect repositories against what docs/defeitos-3.md says about them.

For each repository: the visible tests pass with the defect and with the fix; every reference
test fails (by assertion, not by collection error) with the defect and passes with the fix; each
bad test is either green with the defect (so the red gate rejects it) or a collection error.
"""

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent / "defeitos"
NAMES = ("pager", "spans", "money", "slugs")
PYTEST = [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "-q", "-rA", "--color=no"]
OUTCOME = re.compile(r"^(PASSED|FAILED|ERROR) (\S+)", re.MULTILINE)


def run(work: Path, *files: str) -> tuple[int, dict[str, str]]:
    done = subprocess.run(
        [*PYTEST, *files], cwd=work, capture_output=True, text=True, encoding="utf-8", check=False
    )
    return done.returncode, {m[2]: m[1] for m in OUTCOME.finditer(done.stdout)}


def copy(name: str, work: Path, *, fixed: bool, extra: Path | None, into: str) -> None:
    shutil.copytree(HERE / name / "repo", work, dirs_exist_ok=True)
    if fixed:
        shutil.copy(HERE / name / "corrigido" / "core.py", work / "src" / name / "core.py")
    if extra is not None:
        target = work / "tests" / into
        target.parent.mkdir(exist_ok=True)
        shutil.copy(extra, target)


def check(name: str) -> list[str]:
    problems: list[str] = []
    for fixed in (False, True):
        state = "fix" if fixed else "defect"
        with tempfile.TemporaryDirectory() as tmp:
            copy(name, Path(tmp), fixed=fixed, extra=None, into="")
            code, seen = run(Path(tmp))
            if code != 0:
                problems.append(f"{name}: visible tests do not pass with the {state}")
    reference = HERE / name / "referencia" / "test_referencia.py"
    for fixed in (False, True):
        with tempfile.TemporaryDirectory() as tmp:
            copy(name, Path(tmp), fixed=fixed, extra=reference, into="test_referencia.py")
            code, seen = run(Path(tmp), "tests/test_referencia.py")
            wanted = "PASSED" if fixed else "FAILED"
            if not seen or any(v != wanted for v in seen.values()):
                problems.append(f"{name}: reference with fixed={fixed} gave {code} {seen}")
    for bad in sorted((HERE / name / "ruins").glob("test_ruim_*.py")):
        with tempfile.TemporaryDirectory() as tmp:
            copy(name, Path(tmp), fixed=False, extra=bad, into=bad.name)
            code, seen = run(Path(tmp), f"tests/{bad.name}")
        broken = "importacao" in bad.name
        if broken and not (code != 0 and "ERROR" in seen.values()):
            problems.append(f"{name}/{bad.name}: expected a collection error, got {code} {seen}")
        if not broken and (code != 0 or "PASSED" not in seen.values()):
            problems.append(f"{name}/{bad.name}: expected green with the defect, got {code} {seen}")
    return problems


def main() -> int:
    problems = [p for name in NAMES for p in check(name)]
    for problem in problems:
        print(problem)
    print("ok" if not problems else f"{len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
