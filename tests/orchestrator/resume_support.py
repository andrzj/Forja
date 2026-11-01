"""The scenario every resume test shares, and the facts that say two runs ended the same way."""

import copy
import re
from typing import Any

from forja.core.events import EventLog
from forja.core.states import AttemptState, Level
from forja.orchestrator.outcome import Outcome
from tests.orchestrator.fakes import ContentMeasurer, ScriptedAgent
from tests.orchestrator.harness import RUN, World


def scenario(world: World, **options: Any) -> tuple[Outcome, EventLog]:
    """One task; the agent first writes work the gate rejects, then work it accepts."""
    options.setdefault("agent", ScriptedAgent(in_process=False, by_feedback=True))
    options.setdefault("measurer", ContentMeasurer())
    return world.run(**options)


def attempt_states(log: EventLog) -> list[AttemptState]:
    states = []
    for attempt in log.state.children_of(Level.ATTEMPT, "t1-s"):
        state = log.state.state_of(Level.ATTEMPT, attempt)
        assert isinstance(state, AttemptState)
        states.append(state)
    return states


def agent_was_running(world: World) -> bool:
    """Whether the log, as the dead process left it, shows an attempt in the middle of its call."""
    probe = world.root / "probe"
    probe.mkdir(exist_ok=True)
    copy_of_log = probe / "events.jsonl"
    copy_of_log.write_bytes((world.run_dir / "events.jsonl").read_bytes())
    with EventLog.open(copy_of_log, RUN) as log:
        if not log.state.has_target(Level.STAGE, "t1-s"):
            return False
        # the call was begun (its intent is in the log) and its result was never acted on
        raw = copy_of_log.read_text(encoding="utf-8")
        return any(
            log.state.state_of(Level.ATTEMPT, a) is AttemptState.AGENT_RUNNING
            and f"call_agent_cli:{a}" in raw
            for a in log.state.children_of(Level.ATTEMPT, "t1-s")
        )


def fingerprint(world: World, log: EventLog) -> dict[str, Any]:
    """The facts two runs must share to have ended in the same place.

    Ids and times are left out because they differ from run to run; commits are compared by tree.
    The summary is included whole: it is written from the log, so it must come out the same.
    """
    state = log.state
    run_branch = world.workspace.run_branch
    attempts: dict[str, int] = {}
    for current in attempt_states(log):
        attempts[current.value] = attempts.get(current.value, 0) + 1
    discards = [
        state.transition_payload(Level.ATTEMPT, a, AttemptState.DISCARDED) or {}
        for a in state.children_of(Level.ATTEMPT, "t1-s")
        if state.state_of(Level.ATTEMPT, a) is AttemptState.DISCARDED
    ]
    return {
        "execution": state.state_of(Level.EXECUTION, RUN).value,
        "task": state.state_of(Level.TASK, "t1").value,
        "stage": state.state_of(Level.STAGE, "t1-s").value,
        "attempts": attempts,
        "infra_failures": sum(1 for d in discards if d.get("infra_failure") is True),
        "open_operations": sorted(state.open_operations),
        "refs": sorted(world.repo.sh("for-each-ref", "--format=%(refname)").splitlines()),
        "run_tree": world.repo.sh("rev-parse", f"{run_branch}^{{tree}}"),
        "commits": world.repo.sh("rev-list", "--count", run_branch),
        "worktrees": len(world.repo.sh("worktree", "list").splitlines()),
        "summary": (world.run_dir / "resumo.md")
        .read_text(encoding="utf-8")
        .replace(str(world.run_dir), "<run>"),
        "blobs": sorted(p.name for p in (world.run_dir / "store" / "blobs").glob("*")),
    }


def with_one_more_discarded_attempt(reference: dict[str, Any]) -> dict[str, Any]:
    """The reference run plus the attempt whose agent call could not be trusted."""
    expected = copy.deepcopy(reference)
    expected["attempts"]["discarded"] = expected["attempts"].get("discarded", 0) + 1
    expected["infra_failures"] += 1
    return expected


NEWLINE = chr(10)
ATTEMPT_LINE = re.compile(r"^(  - `)(.+)-a\d+(`.*)$")


def without_discarded_in_summary(settled: dict[str, Any]) -> dict[str, Any]:
    """The same facts with the summary read as if the interrupted call had never been listed.

    The summary names every attempt, so the one a restart discards shows up in it and shifts the
    numbers after it; `with_one_more_discarded_attempt` accounts for it in the counts instead.
    """
    counts: dict[str, int] = {}
    kept = []
    for line in settled["summary"].split(NEWLINE):
        found = ATTEMPT_LINE.match(line)
        if found and "descartada (infraestrutura)" in line:
            continue
        if found:
            counts[found[2]] = counts.get(found[2], 0) + 1
            line = f"{found[1]}{found[2]}-a{counts[found[2]]}{found[3]}"
        kept.append(line)
    return {**settled, "summary": NEWLINE.join(kept)}
