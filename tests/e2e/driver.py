"""A scripted run through every operation of the idempotency table, resumable from its own log.

This is a test double for the orchestrator, not the orchestrator. Every step looks at the log and
skips what it already records, so running it again after any interruption continues instead of
starting over. Real pieces do the work: event log, process runner, git, manifests, artifacts.
"""

import asyncio
import hashlib
import os
import shutil
import sys
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from pydantic import JsonValue

from forja.core.artifacts import ArtifactStore
from forja.core.artifacts.models import ArtifactType, Producer
from forja.core.artifacts.schemas import ExecutionSummaryBody, TaskOutcome, TaskOutcomeKind
from forja.core.atomic import atomic_write_bytes
from forja.core.events import EventLog, LogEventSink, OpenOperation
from forja.core.idempotency import (
    Reconciliation,
    reconcile_apply_diff,
    reconcile_call_agent_cli,
    reconcile_commit_stage,
    reconcile_create_attempt_worktree,
    reconcile_create_task_branch,
    reconcile_integrate_task,
    reconcile_prepare_workcopy,
    reconcile_push_run_branch,
    reconcile_remove_worktree,
    reconcile_run_tool,
    task_branch_name,
)
from forja.core.manifest import build_manifest
from forja.core.process import ProcessRunner, ProcessSpec
from forja.core.states import AttemptState, ExecutionState, Level, StageState, TaskState
from tests.e2e.world import RUN, RUN_BRANCH, STAGE, TASK, World

TASK_BRANCH = task_branch_name(RUN, TASK)
AGENT = Path(__file__).with_name("agent.py")
PAUSE_ENV = "E2E_AGENT_PAUSE"
STALL_ENV = "E2E_STALL"
TORN_ENV = "E2E_TORN_AT"
STALLED_MARKER = "stalled"

_STILL_VALIDATING = (
    AttemptState.AGENT_RUNNING,
    AttemptState.VALIDATING,
    AttemptState.APPROVED,
)
Work = Callable[[], object]
Payload = Callable[[], dict[str, JsonValue]]


class Interrupted(Exception):
    """Stands for the process dying at this point."""


def stall_from_environment(world: World) -> Callable[[str], None]:
    """Freeze at the point named in ``E2E_STALL`` so a test can kill this process there."""
    wanted = os.environ.get(STALL_ENV)

    def stall(point: str) -> None:
        if point == wanted:
            (world.root / STALLED_MARKER).write_text(point)
            time.sleep(120)

    return stall


def torn_write_from_environment(world: World) -> Callable[[int, bytes], int]:
    """Write half of the Nth line named in ``E2E_TORN_AT`` and freeze, as a power cut would."""
    at = int(os.environ.get(TORN_ENV, "0"))
    count = 0

    def write(fd: int, data: bytes) -> int:
        nonlocal count
        count += 1
        if at and count == at:
            os.write(fd, data[: len(data) // 2])
            (world.root / STALLED_MARKER).write_text(f"write {at}")
            time.sleep(120)
        return os.write(fd, data)

    return write


class CrashAfter:
    """A ``write`` that lets ``writes`` lines through, then fails, maybe leaving half a line."""

    def __init__(self, writes: int, *, torn: bool = False) -> None:
        self.writes = writes
        self.torn = torn
        self.count = 0

    def __call__(self, fd: int, data: bytes) -> int:
        self.count += 1
        if self.count > self.writes:
            if self.torn:
                os.write(fd, data[: len(data) // 2])
            raise Interrupted(f"after {self.writes} lines")
        return os.write(fd, data)


class FileEvidenceIndex:
    def __init__(self, folder: Path) -> None:
        self._folder = folder

    def has(self, cache_key: str) -> bool:
        return (self._folder / f"{cache_key}.json").is_file()


def reconciler(world: World) -> Callable[[OpenOperation], Awaitable[Reconciliation]]:
    """One real reconciler per operation, fed from what the intent recorded."""
    git = world.reconciling_git()
    index = FileEvidenceIndex(world.evidence_dir)

    async def reconcile(op: OpenOperation) -> Reconciliation:
        p: Any = op.payload
        match op.operation:
            case "create_task_branch":
                return await reconcile_create_task_branch(git, p["branch"])
            case "create_attempt_worktree":
                return await reconcile_create_attempt_worktree(
                    git, Path(p["worktree"]), p["expected_head"]
                )
            case "prepare_workcopy":
                return reconcile_prepare_workcopy(Path(p["workcopy"]), p["expected_digest"])
            case "call_agent_cli":
                return reconcile_call_agent_cli()
            case "apply_diff":
                return reconcile_apply_diff(Path(p["worktree"]), p["expected_digest"])
            case "run_tool":
                return reconcile_run_tool(index, p["cache_key"])
            case "commit_stage":
                return await reconcile_commit_stage(git, p["task_branch"], p["stage_id"])
            case "integrate_task":
                return await reconcile_integrate_task(git, p["task_branch"], p["run_branch"])
            case "remove_worktree":
                return await reconcile_remove_worktree(git, Path(p["worktree"]))
            case "push_run_branch":
                return await reconcile_push_run_branch(git, "origin", p["branch"])
        raise AssertionError(f"no reconciler for {op.operation}")

    return reconcile


class Script:
    def __init__(
        self, world: World, log: EventLog, stall: Callable[[str], None] = lambda _point: None
    ) -> None:
        self.world = world
        self.log = log
        self.stall = stall
        self.store = ArtifactStore(world.store_dir)

    # -- log-driven building blocks ---------------------------------------------------------

    def enter(
        self,
        level: Level,
        target: str,
        to: Any,
        *,
        parent: str | None = None,
        payload: dict[str, JsonValue] | None = None,
        refs: Any = (),
    ) -> None:
        """Move ``target`` into ``to`` unless the log shows it was already there."""
        state = self.log.state
        if not state.has_target(level, target):
            self.log.append_transition(
                level, target, None, to, parent_id=parent, payload=payload, refs=refs
            )
        elif state.transition_payload(level, target, to) is None:
            current = state.state_of(level, target)
            self.log.append_transition(level, target, current, to, payload=payload, refs=refs)

    def operation_id(self, name: str, target: str) -> str | None:
        """The id to run ``name`` under, or ``None`` if the log shows it already happened."""
        retry = 0
        while True:
            candidate = f"{name}:{target}" + (f":{retry}" if retry else "")
            effect = self.log.state.effect_of(candidate)
            if effect is None:
                if candidate in self.log.state.open_operations:
                    raise AssertionError(f"{candidate} is still open; resume first")
                return candidate
            if effect.get("reconciled") != "redo":
                return None
            retry += 1

    def operate(
        self, name: str, level: Level, target: str, payload: Payload, work: Work, subject: str
    ) -> None:
        op_id = self.operation_id(name, subject)
        if op_id is None:
            return
        self.log.append_intent(level, target, name, op_id, payload=payload())
        self.stall(f"{name}:after_intent")
        work()
        self.stall(f"{name}:before_effect")
        self.log.append_effect(level, target, name, op_id)

    # -- the script -------------------------------------------------------------------------

    async def run(self) -> None:
        w = self.world
        for state in (
            ExecutionState.PREPARING,
            ExecutionState.CONFIRMED,
            ExecutionState.MEASURING_BASELINE,
            ExecutionState.PLANNING,
            ExecutionState.EXECUTING,
        ):
            self.enter(Level.EXECUTION, RUN, state)
        self.enter(Level.TASK, TASK, TaskState.PENDING, parent=RUN)
        self.enter(Level.TASK, TASK, TaskState.IN_PROGRESS)
        self.operate(
            "create_task_branch",
            Level.TASK,
            TASK,
            lambda: {"branch": TASK_BRANCH},
            lambda: w.sh("branch", TASK_BRANCH, RUN_BRANCH),
            TASK,
        )
        self.enter(Level.STAGE, STAGE, StageState.PENDING, parent=TASK)
        self.enter(Level.STAGE, STAGE, StageState.IN_PROGRESS)

        while (attempt := self._next_attempt()) is not None:
            await self._attempt(attempt)

        self.operate(
            "integrate_task",
            Level.TASK,
            TASK,
            lambda: {"task_branch": TASK_BRANCH, "run_branch": RUN_BRANCH},
            lambda: w.sh("merge", "--ff-only", TASK_BRANCH),
            TASK,
        )
        self.enter(Level.TASK, TASK, TaskState.INTEGRATED)
        self.enter(Level.EXECUTION, RUN, ExecutionState.CLOSING)
        self.operate(
            "push_run_branch",
            Level.EXECUTION,
            RUN,
            lambda: {"branch": RUN_BRANCH},
            lambda: w.sh("push", "origin", RUN_BRANCH),
            RUN,
        )
        summary = self.store.put(
            artifact_type=ArtifactType.EXECUTION_SUMMARY,
            producer=Producer.FORJA,
            body=self._summary(),
            artifact_id="summary",
        )
        self.enter(Level.EXECUTION, RUN, ExecutionState.DELIVERED, refs=[self.store.ref(summary)])

    def _next_attempt(self) -> str | None:
        state = self.log.state
        children = state.children_of(Level.ATTEMPT, STAGE)
        for attempt in children:
            if self.operation_id("remove_worktree", attempt) is not None:
                return attempt
        if state.state_of(Level.STAGE, STAGE) is StageState.IN_PROGRESS:
            return f"a{len(children) + 1}"
        return None

    def _summary(self) -> ExecutionSummaryBody:
        state = self.log.state
        counted = [
            state.state_of(Level.ATTEMPT, a)
            for a in state.children_of(Level.ATTEMPT, STAGE)
            if state.state_of(Level.ATTEMPT, a) is not AttemptState.DISCARDED
        ]
        return ExecutionSummaryBody(
            tasks=(
                TaskOutcome(
                    task_id=TASK,
                    outcome=TaskOutcomeKind.INTEGRATED,
                    attempts=len(counted),
                    rejected_attempts=counted.count(AttemptState.REJECTED),
                ),
            )
        )

    async def _attempt(self, attempt: str) -> None:
        w = self.world
        state = self.log.state
        folder = w.attempt_dir(attempt)
        worktree, workcopy = folder / "wt", folder / "copy"

        self.enter(Level.ATTEMPT, attempt, AttemptState.CREATED, parent=STAGE)
        self.operate(
            "create_attempt_worktree",
            Level.ATTEMPT,
            attempt,
            lambda: {"worktree": str(worktree), "expected_head": w.sh("rev-parse", TASK_BRANCH)},
            lambda: self._add_worktree(worktree),
            attempt,
        )
        self.operate(
            "prepare_workcopy",
            Level.ATTEMPT,
            attempt,
            lambda: {
                "workcopy": str(workcopy),
                "expected_digest": build_manifest(worktree, exclude={".git"}).digest(),
            },
            lambda: self._copy(worktree, workcopy),
            attempt,
        )
        self.enter(Level.ATTEMPT, attempt, AttemptState.WORKCOPY_READY)
        self.enter(Level.ATTEMPT, attempt, AttemptState.AGENT_RUNNING)
        await self._agent(attempt, workcopy)

        # Worktrees of finished attempts may be half removed; only unfinished ones are read again.
        if state.state_of(Level.ATTEMPT, attempt) in _STILL_VALIDATING:
            self.enter(Level.ATTEMPT, attempt, AttemptState.VALIDATING)
            self.operate(
                "apply_diff",
                Level.ATTEMPT,
                attempt,
                lambda: {
                    "worktree": str(worktree),
                    "expected_digest": build_manifest(workcopy).digest(),
                },
                lambda: self._mirror(workcopy, worktree),
                attempt,
            )
            key = self._cache_key(worktree)
            self.operate(
                "run_tool",
                Level.ATTEMPT,
                attempt,
                lambda: {"cache_key": key},
                lambda: self._check(worktree, key),
                attempt,
            )
            approved = self._evidence_says_ok(key)
            self.enter(
                Level.ATTEMPT,
                attempt,
                AttemptState.APPROVED if approved else AttemptState.REJECTED,
                payload={"cache_key": key},
            )
            if approved:
                self._commit(attempt, worktree)

        if state.state_of(Level.ATTEMPT, attempt) is AttemptState.COMMITTED:
            self.enter(Level.STAGE, STAGE, StageState.COMMITTED)
        self.operate(
            "remove_worktree",
            Level.ATTEMPT,
            attempt,
            lambda: {"worktree": str(worktree)},
            lambda: self._remove_worktree(worktree),
            attempt,
        )

    def _commit(self, attempt: str, worktree: Path) -> None:
        w = self.world

        def work() -> None:
            # Back to the task tip first: a commit made before an interruption is replaced by the
            # same one, not stacked on top of itself.
            w.sh("reset", "--soft", TASK_BRANCH, cwd=worktree)
            w.sh("add", "-A", cwd=worktree)
            w.sh(
                "commit",
                "-m",
                "implement the stage",
                "--trailer",
                f"Task-Id: {TASK}",
                "--trailer",
                f"Stage-Id: {STAGE}",
                "--trailer",
                f"Attempt-Id: {attempt}",
                cwd=worktree,
            )
            w.sh("update-ref", f"refs/heads/{TASK_BRANCH}", "HEAD", cwd=worktree)

        self.operate(
            "commit_stage",
            Level.ATTEMPT,
            attempt,
            lambda: {"task_branch": TASK_BRANCH, "stage_id": STAGE},
            work,
            attempt,
        )
        self.enter(Level.ATTEMPT, attempt, AttemptState.COMMITTED)

    async def _agent(self, attempt: str, workcopy: Path) -> None:
        op_id = self.operation_id("call_agent_cli", attempt)
        if op_id is None:
            return
        state = self.log.state
        rejected = sum(
            state.state_of(Level.ATTEMPT, a) is AttemptState.REJECTED
            for a in state.children_of(Level.ATTEMPT, STAGE)
        )
        content = "good" if rejected else "bad"
        pause = os.environ.get(PAUSE_ENV, "0")
        spec = ProcessSpec(
            [sys.executable, str(AGENT), "out.txt", content, pause],
            workcopy,
            self.world.env,
            60,
        )
        sink = LogEventSink(self.log, Level.ATTEMPT, attempt, "call_agent_cli")
        result = await ProcessRunner(sink).run(
            op_id, spec, self.world.logs_dir / f"{op_id.replace(':', '-')}.log"
        )
        assert result.exit_code == 0, result

    # -- the work the operations do ---------------------------------------------------------

    def _add_worktree(self, worktree: Path) -> None:
        w = self.world
        if worktree.exists():
            shutil.rmtree(worktree, ignore_errors=True)
        w.sh("worktree", "prune")
        w.sh("worktree", "add", "--detach", str(worktree), TASK_BRANCH)

    @staticmethod
    def _copy(source: Path, target: Path) -> None:
        shutil.rmtree(target, ignore_errors=True)
        shutil.copytree(source, target, ignore=shutil.ignore_patterns(".git"))

    @staticmethod
    def _mirror(source: Path, target: Path) -> None:
        for entry in target.iterdir():
            if entry.name == ".git":
                continue
            if entry.is_dir():
                shutil.rmtree(entry)
            else:
                entry.unlink()
        shutil.copytree(source, target, dirs_exist_ok=True)

    def _remove_worktree(self, worktree: Path) -> None:
        w = self.world
        if worktree.exists():
            w.sh("worktree", "remove", "--force", str(worktree))
        shutil.rmtree(worktree, ignore_errors=True)
        w.sh("worktree", "prune")

    @staticmethod
    def _cache_key(worktree: Path) -> str:
        scope = hashlib.sha256((worktree / "out.txt").read_bytes()).hexdigest()
        return hashlib.sha256(f"fake-check\0{scope}".encode()).hexdigest()

    def _check(self, worktree: Path, key: str) -> None:
        ok = (worktree / "out.txt").read_text(encoding="utf-8") == "good"
        body = f'{{"tool": "fake-check", "ok": {str(ok).lower()}}}\n'.encode()
        atomic_write_bytes(self.world.evidence_dir / f"{key}.json", body)

    def _evidence_says_ok(self, key: str) -> bool:
        return b'"ok": true' in (self.world.evidence_dir / f"{key}.json").read_bytes()


async def drive(world: World, log: EventLog, stall: Callable[[str], None] | None = None) -> None:
    await Script(world, log, stall or (lambda _point: None)).run()


def main() -> None:
    """Run the script in this process; a test kills it where the environment says to stall."""
    world = World(Path(sys.argv[1]))
    stall = stall_from_environment(world)
    log = world.open_log(write=torn_write_from_environment(world))
    asyncio.run(drive(world, log, stall))
    log.close()


if __name__ == "__main__":
    main()
