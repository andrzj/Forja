"""The agent runner for a real CLI: a copy of the worktree without git, the call, the way back.

The agent works in a copy, so it cannot touch git or the other worktrees. Its work comes back only
if it declared what it did (``.forja-agent/saida.json``, the output contract of every role) and the
declaration matches the files that really changed. What the CLI prints is read as it arrives: it
becomes activity and token events, and a CLI that stays silent for too long is ended.
"""

import asyncio
import contextlib
import re
import shutil
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from forja.core.adapters.common import build_spec
from forja.core.adapters.executor import (
    AGENT_DIR,
    AgentActivity,
    AgentRequest,
    CommandActivity,
    ErrorActivity,
    ErrorKind,
    ExecutorAdapter,
    FileEditActivity,
    FileReadActivity,
    RolePermissions,
    TextActivity,
    UsageActivity,
)
from forja.core.artifacts.errors import InvalidLlmOutput
from forja.core.artifacts.llm_output import (
    ChangeDeclaration,
    LlmOutput,
    compare_with_diff,
    parse_llm_output,
)
from forja.core.artifacts.models import Producer
from forja.core.events import EventLog, OpenOperation
from forja.core.idempotency import (
    Reconciliation,
    reconcile_apply_diff,
    reconcile_prepare_workcopy,
)
from forja.core.isolation import SensitivePaths
from forja.core.manifest import (
    EntryKind,
    Manifest,
    ManifestDiff,
    ManifestEntry,
    build_manifest,
    diff_manifests,
    find_violations,
)
from forja.core.process import EventSink, ProcessIdentity, ProcessRunner
from forja.core.redaction import PackageItem, Redactor
from forja.core.redaction.engine import ItemKind
from forja.core.states import Level
from forja.orchestrator.budget import AGENT_ACTIVITY
from forja.orchestrator.operations import Step
from forja.orchestrator.ports import AgentResult, AttemptContext, RejectedWork

PACKAGE = "package.md"
OUTPUT = "saida.json"
IDLE_LIMIT = 300.0  # seconds without a single line of output: the CLI is stuck, not working
OPERATION = "call_agent_cli"

INSTRUCTIONS = """\
You are refactoring existing code. The behaviour must stay exactly the same: same results, same
public names, same side effects. Do not change tests and do not add dependencies.

You cannot run commands. Read the files you need and change them with the edit tools.

When you are done, write the file `{agent_dir}/{output}` with this shape and nothing else, listing
every file you created, modified or removed (the list is checked against what really changed):

{{"actions": [{{"summary": "what changed", "reason": "why it is better",
"files": [{{"path": "relative/path.py", "change": "modified"}}]}}]}}

`change` is one of `created`, `modified`, `removed`. Add `"assumptions"` only for something you
had to guess. Then answer with one short sentence.
"""


_SHORT_NAME = re.compile(r"~\d")


def plain(path: str) -> str:
    """The path as Windows would read it: trailing dots and spaces of each part are dropped."""
    return "/".join(part.rstrip(" .") for part in path.replace("\\", "/").split("/"))


def touches_git(path: str) -> bool:
    """Whether a path goes through git's own directory, by any spelling the system would accept.

    Windows ignores trailing dots and spaces and has short names (``GIT~1``), and the file system
    may fold case, so each part is compared in a normal form.
    """
    for part in path.replace("\\", "/").split("/"):
        plain = part.casefold().rstrip(" .")
        if plain == ".git" or plain.startswith("git~"):
            return True
    return False


def _wipe(directory: Path, keep: frozenset[str], prefix: str = "") -> None:
    """Empty ``directory`` of everything but git's own entry and the paths in ``keep``."""
    for entry in directory.iterdir():
        relative = f"{prefix}{entry.name}"
        if (not prefix and entry.name == ".git") or relative in keep:
            continue
        if entry.is_dir() and not (entry.is_symlink() or entry.is_junction()):
            _wipe(entry, keep, f"{relative}/")
            if not any(entry.iterdir()):
                entry.rmdir()
        else:
            entry.unlink()


def _refuse_links_on_the_way(worktree: Path, path: str) -> None:
    """Writing into the worktree must never go through a link that is already there."""
    parts = path.split("/")
    for i in range(len(parts)):
        step = worktree.joinpath(*parts[: i + 1])
        if step.is_symlink() or step.is_junction():
            raise RuntimeError(f"{path} would be written through a link in the worktree")


def workcopy_of(ctx: AttemptContext) -> Path:
    return ctx.worktree.with_name(f"{ctx.attempt_id}-copy")


def _fence(text: str) -> str:
    """A code fence longer than any run of backticks inside the text."""
    ticks = 3
    while "`" * ticks in text:
        ticks += 1
    return "`" * ticks


def build_package(ctx: AttemptContext, redactor: Redactor) -> str:
    """The text the agent receives: the task, the rules, the files in scope and the last verdict."""
    task = ctx.task
    items, notes = [], []
    for name in task.scope:
        path = ctx.worktree / name
        if path.is_file():
            items.append(PackageItem(ItemKind.FILE, name, path.read_text(encoding="utf-8"), True))
        else:
            notes.append(f"`{name}` is a directory: read the files you need from it.")
    result = redactor.redact(items)
    parts = [
        f"# Task\n\n{task.intent}\n",
        INSTRUCTIONS.format(agent_dir=AGENT_DIR, output=OUTPUT),
        "## What you may change\n",
        f"Only inside: {', '.join(f'`{name}`' for name in task.scope)}.",
        f"At most {task.max_files} files and {task.max_lines} changed lines.\n",
    ]
    if result.items or notes:
        parts.append("## Files in scope\n")
    for item in result.items:
        fence = _fence(item.content)
        parts.append(f"### `{item.name}`\n\n{fence}\n{item.content}\n{fence}\n")
    parts += notes
    for dropped in result.dropped:
        parts.append(f"`{dropped.name}` was withheld ({dropped.reason.value}).")
    if ctx.previous_rejection:
        parts.append(f"## The previous attempt was rejected\n\n{ctx.previous_rejection}\n")
    return "\n".join(parts) + "\n"


class Watch:
    """Passes the runner's reports on, reads the CLI's output as activity, notes when it spoke."""

    def __init__(
        self,
        inner: EventSink,
        log: EventLog,
        ctx: AttemptContext,
        adapter: ExecutorAdapter,
        clock: Callable[[], float],
    ) -> None:
        self._inner, self._log, self._ctx = inner, log, ctx
        self._adapter, self._clock = adapter, clock
        self.last_output = clock()
        self.error: ErrorActivity | None = None
        self.operation_id = ""

    def intent(self, operation_id: str, details: Mapping[str, object]) -> None:
        self.operation_id = operation_id
        self._inner.intent(operation_id, details)

    def started(self, operation_id: str, identity: ProcessIdentity) -> None:
        self._inner.started(operation_id, identity)

    def effect(self, operation_id: str, details: Mapping[str, object]) -> None:
        self._inner.effect(operation_id, details)

    def progress(self, operation_id: str, channel: str, line: str) -> None:
        self.last_output = self._clock()
        self._inner.progress(operation_id, channel, line)
        if channel != "out":
            return
        activity = self._adapter.parse_event(line)
        if activity is None:
            return
        if isinstance(activity, ErrorActivity):
            self.error = activity
        self._log.append_progress(
            Level.ATTEMPT,
            self._ctx.attempt_id,
            AGENT_ACTIVITY,
            operation=OPERATION,
            operation_id=operation_id,
            payload=_payload(activity),
        )


def _payload(activity: AgentActivity) -> dict[str, Any]:
    match activity:
        case UsageActivity(input_tokens, output_tokens):
            return {"type": "usage", "input": input_tokens or 0, "output": output_tokens or 0}
        case TextActivity(text):
            return {"type": "text", "text": text[:200]}
        case FileReadActivity(path):
            return {"type": "file_read", "path": path}
        case FileEditActivity(path, added, removed):
            return {"type": "file_edit", "path": path, "added": added, "removed": removed}
        case CommandActivity(command, exit_code):
            return {"type": "command", "command": command[:200], "exit_code": exit_code}
        case ErrorActivity(message, kind):
            return {"type": "error", "message": message[:200], "kind": kind.value}
    raise AssertionError(activity)


class ExecutorAgentRunner:
    """``AgentRunner`` over any ``ExecutorAdapter``; the CLI itself is the user's to have set up."""

    def __init__(
        self,
        adapter: ExecutorAdapter,
        executable: Path,
        host_env: Mapping[str, str],
        log: EventLog,
        *,
        redactor: Redactor | None = None,
        sensitive: SensitivePaths | None = None,
        role: Producer = Producer.IMPLEMENTER,
        permissions: RolePermissions = RolePermissions(can_edit_files=True),  # noqa: B008
        idle_limit: float = IDLE_LIMIT,
        poll: float = 1.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._adapter, self._executable, self._env, self._log = adapter, executable, host_env, log
        self._sensitive = sensitive or SensitivePaths.with_defaults()
        self._redactor = redactor or Redactor(sensitive=self._sensitive)
        self._role, self._permissions = role, permissions
        self._idle_limit, self._poll, self._clock = idle_limit, poll, clock

    # -- the copy the agent works in ------------------------------------------------------------

    def prepare_workcopy(self, ctx: AttemptContext) -> Step:
        target = workcopy_of(ctx)

        async def payload() -> dict[str, Any]:
            seen = self._visible(build_manifest(ctx.worktree, exclude={".git"}))
            return {"workcopy": str(target), "expected_digest": seen.digest()}

        async def run() -> None:
            shutil.rmtree(target, ignore_errors=True)
            shutil.copytree(ctx.worktree, target, ignore=self._left_out(ctx.worktree))
            agent_dir = target / AGENT_DIR
            agent_dir.mkdir()
            package = build_package(ctx, self._redactor)
            (agent_dir / PACKAGE).write_text(package, encoding="utf-8", newline="\n")
            setup = self._adapter.permission_setup(self._role, self._permissions)
            for name, data in setup.files.items():
                (agent_dir / name).write_bytes(data)

        return Step(payload, run)

    # -- the call ---------------------------------------------------------------------------------

    async def call(self, ctx: AttemptContext, operation_id: str, sink: EventSink) -> AgentResult:
        workcopy = workcopy_of(ctx)
        request = AgentRequest(
            self._role, workcopy / AGENT_DIR / PACKAGE, workcopy, self._permissions
        )
        setup = self._adapter.permission_setup(self._role, self._permissions)
        plan = self._adapter.plan_invocation(request, setup, self._executable)
        spec = build_spec(plan, self._env, timeout=None)
        watch = Watch(sink, self._log, ctx, self._adapter, self._clock)
        log_path = ctx.worktree.parent / f"{operation_id}.log"
        task = asyncio.create_task(ProcessRunner(watch).run(operation_id, spec, log_path))
        stalled = False
        try:
            while not task.done():
                await asyncio.wait({task}, timeout=self._poll)
                if not task.done() and self._clock() - watch.last_output > self._idle_limit:
                    stalled = True
                    break
        finally:
            if not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
        if stalled:
            message = f"the agent printed nothing for {self._idle_limit:.0f} seconds"
            return AgentResult(error=ErrorActivity(message, ErrorKind.TRANSIENT))
        if watch.error is not None:
            return AgentResult(error=watch.error)
        result = task.result()
        if result.exit_code != 0:
            message = (
                f"the agent CLI ended with {result.outcome.value}, exit code {result.exit_code}"
            )
            return AgentResult(error=ErrorActivity(message, ErrorKind.TRANSIENT))
        return AgentResult(reason=_reason(workcopy))

    # -- the way back -----------------------------------------------------------------------------

    def apply_diff(self, ctx: AttemptContext) -> Step:
        source = workcopy_of(ctx)

        async def payload() -> dict[str, Any]:
            declaration = ChangeDeclaration.from_output(_declared(source))
            after = build_manifest(source, exclude={AGENT_DIR})
            hidden = self._hidden(ctx.worktree)
            before = self._visible(build_manifest(ctx.worktree, exclude={".git"}))
            self._refuse_tampering(source)
            self._refuse_off_limits(after, diff_manifests(before, after))
            self._refuse_collisions(after, hidden)
            problems = find_violations(after, destination_root=ctx.worktree)
            if problems:
                raise RejectedWork("; ".join(f"{p.path}: {p.detail}" for p in problems))
            differences = compare_with_diff(declaration, diff_manifests(before, after))
            if differences:
                raise RejectedWork(
                    "the files declared are not the files changed: "
                    + "; ".join(
                        f"{d.path} declared {d.declared or 'nothing'}, "
                        f"changed {d.actual or 'nothing'}"
                        for d in differences
                    )
                )
            kept = Manifest({**after.entries, **hidden})
            return {"worktree": str(ctx.worktree), "expected_digest": kept.digest()}

        async def run() -> None:
            kept = self._hidden(ctx.worktree)
            _wipe(ctx.worktree, frozenset(kept))
            for path in build_manifest(source, exclude={AGENT_DIR}).entries:
                _refuse_links_on_the_way(ctx.worktree, path)
            shutil.copytree(
                source,
                ctx.worktree,
                dirs_exist_ok=True,
                ignore=shutil.ignore_patterns(AGENT_DIR, ".git"),
            )
            if self._hidden(ctx.worktree) != kept:
                raise RuntimeError("a file that was to stay untouched changed on the way back")

        return Step(payload, run)

    async def reconcile(self, operation: OpenOperation) -> Reconciliation:
        p: Any = operation.payload
        if operation.operation == "prepare_workcopy":
            return reconcile_prepare_workcopy(
                Path(p["workcopy"]), p["expected_digest"], exclude={AGENT_DIR}
            )
        return reconcile_apply_diff(Path(p["worktree"]), p["expected_digest"])

    # -- what the agent may not see or touch ------------------------------------------------------

    def _hidden(self, worktree: Path) -> dict[str, ManifestEntry]:
        """The sensitive files: they stay out of the copy and come back untouched."""
        entries = build_manifest(worktree, exclude={".git"}).entries
        return {path: e for path, e in entries.items() if self._is_hidden(path, e)}

    def _is_hidden(self, path: str, entry: ManifestEntry) -> bool:
        # a link may point at anything, so the agent gets neither it nor what it points at
        return entry.kind is EntryKind.SYMLINK or self._sensitive.matches(plain(path))

    def _visible(self, manifest: Manifest) -> Manifest:
        return Manifest({p: e for p, e in manifest.entries.items() if not self._is_hidden(p, e)})

    def _left_out(self, worktree: Path) -> Callable[[str, list[str]], set[str]]:
        def ignore(directory: str, names: list[str]) -> set[str]:
            relative = Path(directory).relative_to(worktree).as_posix()
            prefix = "" if relative == "." else f"{relative}/"
            return {
                name
                for name in names
                if (not prefix and name == ".git")
                or (Path(directory) / name).is_symlink()
                or (Path(directory) / name).is_junction()
                or self._sensitive.matches(plain(f"{prefix}{name}"))
            }

        return ignore

    def _refuse_off_limits(self, after: Manifest, changed: ManifestDiff) -> None:
        """Git's own files and the sensitive ones are not the agent's to write, whatever it says.

        The copy holds none of the sensitive files, so any it holds the agent made. Names are read
        the way Windows reads them, where ``.env.`` and ``.env `` are ``.env``, and a short name
        (``ENV~1``) can stand for a long one, so no new name may look like one.
        """
        for path in after.entries:
            if touches_git(path):
                raise RejectedWork(f"{path}: the work reaches into git's own directory")
            if self._sensitive.matches(plain(path)):
                raise RejectedWork(f"{path}: the work creates or changes a sensitive file")
        for path in (*changed.created, *changed.modified):
            if any(_SHORT_NAME.search(part) for part in path.split("/")):
                raise RejectedWork(f"{path}: a name with a short-name marker (~digit) is refused")

    def _refuse_collisions(self, after: Manifest, hidden: Mapping[str, ManifestEntry]) -> None:
        """Nothing may be written at a hidden path or below it: below a link it would go through."""
        taken = {plain(path).casefold() for path in hidden}
        for path in after.entries:
            parts = plain(path).casefold().split("/")
            if any("/".join(parts[: i + 1]) in taken for i in range(len(parts))):
                raise RejectedWork(f"{path}: the work goes where it may not write")

    def _refuse_tampering(self, source: Path) -> None:
        """The agent writes in its own directory; its permissions are not for it to change."""
        setup = self._adapter.permission_setup(self._role, self._permissions)
        for name, data in setup.files.items():
            kept = source / AGENT_DIR / name
            if not kept.is_file() or kept.read_bytes() != data:
                raise RejectedWork(f"{AGENT_DIR}/{name}: the agent changed its own permissions")


def _declared(workcopy: Path) -> LlmOutput:
    """What the agent said it did; a missing or malformed declaration rejects the work."""
    path = workcopy / AGENT_DIR / OUTPUT
    if not path.is_file():
        raise RejectedWork(f"{AGENT_DIR}/{OUTPUT} was not written")
    try:
        return parse_llm_output(path.read_bytes())
    except InvalidLlmOutput as error:
        raise RejectedWork(
            f"{AGENT_DIR}/{OUTPUT} is not valid: " + "; ".join(error.problems)
        ) from None


def _reason(workcopy: Path) -> str:
    try:
        return " ".join(action.reason for action in _declared(workcopy).actions)
    except RejectedWork:
        return ""  # apply_diff rejects the work with the details
