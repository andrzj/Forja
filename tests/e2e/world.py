"""The disk a scripted run works on, and the comparison that says two runs ended the same."""

import copy
import hashlib
import os
import shutil
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from forja.core.events import EventLog
from forja.core.idempotency import Git
from forja.core.states import AttemptState, Level

RUN = "run1"
TASK = "t1"
STAGE = "s1"
RUN_BRANCH = f"forja-run/{RUN}"


def minimal_env(home: Path) -> dict[str, str]:
    env = {
        "PATH": os.environ["PATH"],
        "HOME": str(home),
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
    }
    if sys.platform == "win32":
        env["SYSTEMROOT"] = os.environ["SYSTEMROOT"]
    return env


@dataclass(frozen=True)
class World:
    """Everything one scripted run touches, under a single root."""

    root: Path

    @property
    def repo(self) -> Path:
        return self.root / "repo"

    @property
    def remote(self) -> Path:
        return self.root / "remote.git"

    @property
    def run_dir(self) -> Path:
        return self.root / "run"

    @property
    def events(self) -> Path:
        return self.run_dir / "events.jsonl"

    @property
    def evidence_dir(self) -> Path:
        return self.run_dir / "evidence"

    @property
    def store_dir(self) -> Path:
        return self.run_dir / "store"

    @property
    def logs_dir(self) -> Path:
        return self.run_dir / "logs"

    @property
    def env(self) -> dict[str, str]:
        return minimal_env(self.root / "home")

    def attempt_dir(self, attempt_id: str) -> Path:
        return self.root / "attempts" / attempt_id

    def sh(self, *args: str, cwd: Path | None = None) -> str:
        completed = subprocess.run(
            ["git", "-c", "user.name=forja", "-c", "user.email=forja@example.com", *args],
            cwd=cwd or self.repo,
            env=self.env,
            capture_output=True,
            text=True,
            check=True,
        )
        return completed.stdout.strip()

    def reconciling_git(self) -> Git:
        return Git(
            self.repo,
            executable=shutil.which("git") or "git",
            env=self.env,
            timeout=60,
            log_dir=self.logs_dir / "reconcile",
        )

    def open_log(self, **kwargs: Any) -> EventLog:
        return EventLog.open(self.events, RUN, **kwargs)


def build_template(path: Path) -> None:
    """A repository with a base commit and the run branch checked out; copied for every run."""
    home = path.parent / "template-home"
    home.mkdir()
    path.mkdir()
    env = minimal_env(home)
    base = ["git", "-c", "user.name=forja", "-c", "user.email=forja@example.com"]
    for args in (
        ["init", "-b", "main"],
        ["config", "core.autocrlf", "false"],
    ):
        subprocess.run([*base, *args], cwd=path, env=env, check=True, capture_output=True)
    (path / "base.txt").write_text("base\n", encoding="utf-8")
    for args in (
        ["add", "base.txt"],
        ["commit", "-m", "base"],
        ["checkout", "-b", RUN_BRANCH],
    ):
        subprocess.run([*base, *args], cwd=path, env=env, check=True, capture_output=True)


def make_world(root: Path, template: Path) -> World:
    world = World(root)
    (root / "home").mkdir(parents=True)
    shutil.copytree(template, world.repo)
    world.sh("init", "--bare", "-b", "main", str(world.remote), cwd=root)
    world.sh("remote", "add", "origin", str(world.remote))
    return world


def fingerprint(world: World) -> dict[str, Any]:
    """The facts two runs must share to have ended in the same place.

    Replaying the log checks its hash chain as a side effect. Ids and timestamps are left out
    because they differ from run to run; commits are compared by tree for the same reason.
    """
    with world.open_log() as log:
        state = log.state
        attempts = state.children_of(Level.ATTEMPT, STAGE)
        discarded = [
            a for a in attempts if state.state_of(Level.ATTEMPT, a) is AttemptState.DISCARDED
        ]
        return {
            "execution": state.state_of(Level.EXECUTION, RUN).value,
            "task": state.state_of(Level.TASK, TASK).value,
            "stage": state.state_of(Level.STAGE, STAGE).value,
            "attempts": dict(Counter(state.state_of(Level.ATTEMPT, a).value for a in attempts)),
            "infra_failures": sum(
                bool(
                    (state.transition_payload(Level.ATTEMPT, a, AttemptState.DISCARDED) or {}).get(
                        "infra_failure"
                    )
                )
                for a in discarded
            ),
            "open_operations": sorted(state.open_operations),
            "refs": sorted(world.sh("for-each-ref", "--format=%(refname)").splitlines()),
            "run_tree": world.sh("rev-parse", f"{RUN_BRANCH}^{{tree}}"),
            "task_tree": world.sh("rev-parse", f"forja/{RUN}/{TASK}^{{tree}}"),
            "commits": world.sh("rev-list", "--count", RUN_BRANCH),
            "worktrees": len(world.sh("worktree", "list", "--porcelain").split("\n\n")),
            "remote_tip_is_local_tip": (
                world.sh("ls-remote", "origin", f"refs/heads/{RUN_BRANCH}").split()[0]
                == world.sh("rev-parse", RUN_BRANCH)
            ),
            "evidence": _files(world.evidence_dir),
            "blobs": sorted(p.name for p in (world.store_dir / "blobs").glob("*")),
        }


def _files(folder: Path) -> list[tuple[str, str]]:
    return sorted(
        (p.name, hashlib.sha256(p.read_bytes()).hexdigest())
        for p in folder.glob("*")
        if p.is_file() and not p.name.startswith(".")
    )


def expected_after_discarding_one_attempt(reference: dict[str, Any]) -> dict[str, Any]:
    """The reference run plus the attempt whose agent call could not be verified."""
    expected = copy.deepcopy(reference)
    expected["attempts"]["discarded"] = expected["attempts"].get("discarded", 0) + 1
    expected["infra_failures"] += 1
    return expected
