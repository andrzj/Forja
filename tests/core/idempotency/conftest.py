import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

from forja.core.idempotency import Git


def _env(home: Path) -> dict[str, str]:
    env = {
        "PATH": os.environ["PATH"],
        "HOME": str(home),
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
    }
    if sys.platform == "win32":
        env["SYSTEMROOT"] = os.environ["SYSTEMROOT"]
    return env


class Repo:
    """A throwaway repository with a plain-subprocess helper for building scenarios."""

    def __init__(self, path: Path, env: dict[str, str], logs: Path) -> None:
        self.path = path
        self.env = env
        self.git = Git(
            path, executable=shutil.which("git") or "git", env=env, timeout=30, log_dir=logs
        )

    def sh(self, *args: str, cwd: Path | None = None) -> str:
        completed = subprocess.run(
            ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
            cwd=cwd or self.path,
            env=self.env,
            capture_output=True,
            text=True,
            check=True,
        )
        return completed.stdout.strip()

    def commit(self, name: str, message: str = "change") -> str:
        (self.path / name).write_text(name)
        self.sh("add", name)
        self.sh("commit", "-m", message)
        return self.sh("rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path: Path) -> Repo:
    home = tmp_path / "home"
    home.mkdir()
    path = tmp_path / "repo"
    path.mkdir()
    result = Repo(path, _env(home), tmp_path / "logs")
    result.sh("init", "-b", "main")
    result.commit("base.txt", "base")
    return result


@pytest.fixture
def new_remote(tmp_path: Path, repo: Repo) -> Callable[[], Path]:
    def make() -> Path:
        remote = tmp_path / "remote.git"
        repo.sh("init", "--bare", "-b", "main", str(remote), cwd=tmp_path)
        return remote

    return make
