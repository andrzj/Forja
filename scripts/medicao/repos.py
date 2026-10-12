"""The repositories of the experiment, each one a git repository at a fixed first commit."""

import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
NEW_LINE = chr(10)
MEDIUM = ("inventory", "scanner")
CONTROLS = {"plain": "a plain function", "shop": "several modules", "web": "a method"}
ALL = (*CONTROLS, *MEDIUM)
IGNORED = shutil.ignore_patterns("__pycache__", ".pytest_cache", ".ruff_cache", "*.pyc")


def git(repo: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", "-c", "user.name=medicao", "-c", "user.email=medicao@example.com", *args],
        cwd=repo, capture_output=True, text=True, check=True, encoding="utf-8",
    )  # fmt: skip
    return done.stdout.strip()


def materialize(name: str, destination: Path) -> Path:
    """Write the repository ``name`` into ``destination`` (which must not exist) and commit it."""
    if name in CONTROLS:
        sys.path.insert(0, str(ROOT))
        from tests.acceptance.samples import SAMPLES  # noqa: PLC0415

        for relative, text in SAMPLES[CONTROLS[name]].files.items():
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8", newline=NEW_LINE)
    else:
        shutil.copytree(HERE / "repos" / name, destination, ignore=IGNORED)
    # in the repository's own style, not the style of the project that holds these files
    subprocess.run(
        [sys.executable, "-m", "ruff", "format", "-q", "--isolated", str(destination)],
        check=True, capture_output=True,
    )  # fmt: skip
    git(destination, "init", "-q", "-b", "main")
    git(destination, "add", ".")
    git(destination, "commit", "-q", "-m", "first commit")
    return destination
