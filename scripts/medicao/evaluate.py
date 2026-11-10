"""The judge of the experiment: the same objective criteria for the tree any arm delivered.

    python evaluate.py <repo name> <initial tree> <final tree>

prints one JSON object. A delivery is accepted when every criterion of the second measurement holds;
a regression is a case of the characterization oracle that no longer gives the recorded outcome.
"""

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
LIMIT = 15
NOISE = {"__pycache__", ".pytest_cache", ".ruff_cache", ".git", ".forja-agent", ".venv"}
TIMEOUT = 600
CRLF, LF = bytes([13, 10]), bytes([10])


def run(command: list[str], cwd: Path, timeout: int = TIMEOUT) -> tuple[int, str]:
    try:
        done = subprocess.run(
            command, cwd=cwd, capture_output=True, text=True, timeout=timeout, encoding="utf-8",
            errors="replace",
        )  # fmt: skip
    except subprocess.TimeoutExpired:
        return 124, "timed out"
    return done.returncode, done.stdout + done.stderr


def files_of(tree: Path) -> dict[str, str]:
    found = {}
    for path in sorted(tree.rglob("*")):
        relative = path.relative_to(tree)
        if path.is_file() and not (set(relative.parts) & NOISE) and path.suffix != ".pyc":
            # a checkout on Windows may write CRLF; the comparison is of content
            text = path.read_bytes().replace(CRLF, LF)
            found[relative.as_posix()] = hashlib.sha256(text).hexdigest()
    return found


def complex_functions(tree: Path) -> set[str]:
    _, out = run([sys.executable, "-m", "lizard", "-C", str(LIMIT), "-w", "src"], tree)
    return {m[1] for m in re.finditer(r"warning: (\w+) has", out)}


def lint_errors(tree: Path) -> int:
    code, out = run(
        [
            sys.executable,
            "-m",
            "ruff",
            "check",
            "--isolated",
            "--no-cache",
            "--output-format",
            "concise",
            ".",
        ],
        tree,
    )
    return (
        len([line for line in out.splitlines() if re.match(r".+:\d+:\d+: ", line)]) if code else 0
    )


def format_clean(tree: Path) -> bool:
    return (
        run(
            [sys.executable, "-m", "ruff", "format", "--check", "--isolated", "--no-cache", "."],
            tree,
        )[0]
        == 0
    )


def leaks(tree: Path) -> int:
    code, _ = run(["gitleaks", "detect", "--no-git", "--no-banner", "--source", "."], tree)
    return 0 if code == 0 else 1


def evaluate(name: str, initial: Path, final: Path) -> dict[str, object]:
    before, after = files_of(initial), files_of(final)
    changed = sorted(p for p in {*before, *after} if before.get(p) != after.get(p))
    outside = [p for p in changed if not (p.startswith("src/") and p.endswith(".py"))]
    compiled = run([sys.executable, "-m", "compileall", "-q", "src"], final)[0] == 0
    tests_code, tests_out = run(
        [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "-q"], final
    )
    still = sorted(complex_functions(final))
    new_lint = max(0, lint_errors(final) - lint_errors(initial))
    criteria = {
        "compiles": compiled,
        "visible_tests": tests_code == 0,
        "format": format_clean(final),
        "lint": new_lint == 0,
        "secrets": leaks(final) <= leaks(initial),
        "complexity": not still,
        "scope": bool(changed) and not outside,
    }
    golden = HERE / "golden" / f"{name}.json"
    regressions: list[str] = []
    if golden.exists() and compiled:
        code, out = run(
            [sys.executable, str(HERE / "oracle.py"), "verify", name, str(final), str(golden)],
            final, timeout=900,
        )  # fmt: skip
        try:
            regressions = json.loads(out.strip().splitlines()[-1])["failed"]
        except (ValueError, KeyError, IndexError):
            regressions = ["oracle did not finish: " + out[-200:]]
    return {
        "repo": name,
        "accepted": all(criteria.values()),
        "criteria": criteria,
        "failed_criteria": [key for key, ok in criteria.items() if not ok],
        "still_complex": still,
        "changed": changed,
        "outside_scope": outside,
        "regression": bool(regressions),
        "regression_cases": len(regressions),
        "regression_examples": regressions[:5],
        "tests_tail": tests_out[-300:] if tests_code else "",
    }


if __name__ == "__main__":
    print(json.dumps(evaluate(sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])), indent=1))
