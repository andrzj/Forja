"""A run left unfinished is found in its repository only, and discarding never deletes."""

from pathlib import Path

from forja.cli.resume import discard, find_unfinished, read_run, removal_commands
from forja.cli.session import new_config
from forja.core.events import EventLog
from forja.core.states import ExecutionState, Level
from forja.orchestrator.phases import confirm_run
from tests.orchestrator.harness import ISOLATION


def make_run(home: Path, run_id: str, repo: Path, *, to: ExecutionState | None = None) -> Path:
    directory = home / "runs" / run_id
    directory.mkdir(parents=True)
    config = new_config(
        repo=repo,
        base_commit="a" * 40,
        executor_name="claude-code",
        executor_path=Path("claude"),
        executor_version="2.0.0",
        tokens=1000,
    )
    log = EventLog.open(directory / "events.jsonl", run_id)
    confirm_run(log, config, ISOLATION)
    if to is not None:
        path = {
            ExecutionState.PAUSED: [ExecutionState.MEASURING_BASELINE, ExecutionState.PAUSED],
            ExecutionState.FAILED: [ExecutionState.MEASURING_BASELINE, ExecutionState.FAILED],
        }[to]
        before = ExecutionState.CONFIRMED
        for state in path:
            log.append_transition(Level.EXECUTION, run_id, before, state, payload={"reason": "x"})
            before = state
    log.close()
    return directory


def test_a_confirmed_run_of_this_repository_is_found(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    make_run(tmp_path / "home", "r1", repo, to=ExecutionState.PAUSED)
    found = find_unfinished(tmp_path / "home", repo)
    assert [(item.run_id, item.state, item.reason) for item in found] == [("r1", "paused", "x")]


def test_a_run_of_another_repository_is_not(tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    make_run(tmp_path / "home", "r1", tmp_path / "a")
    assert find_unfinished(tmp_path / "home", tmp_path / "b") == []


def test_without_runs_or_with_a_log_never_confirmed_there_is_nothing(tmp_path: Path) -> None:
    assert find_unfinished(tmp_path / "home", tmp_path) == []
    (tmp_path / "home" / "runs" / "r9").mkdir(parents=True)
    assert read_run(tmp_path / "home" / "runs" / "r9") is None
    assert find_unfinished(tmp_path / "home", tmp_path) == []


def test_discarding_a_paused_run_ends_it_and_keeps_the_log(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    directory = make_run(tmp_path / "home", "r1", repo, to=ExecutionState.PAUSED)
    discard(directory)
    assert (directory / "events.jsonl").exists()
    assert find_unfinished(tmp_path / "home", repo) == []
    assert read_run(directory) == (str(repo), "discarded", "discarded_by_user")


def test_discarding_works_from_a_run_that_only_got_confirmed(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    directory = make_run(tmp_path / "home", "r1", repo)
    discard(directory)
    assert find_unfinished(tmp_path / "home", repo) == []


def test_discarding_a_failed_run(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    directory = make_run(tmp_path / "home", "r1", repo, to=ExecutionState.FAILED)
    discard(directory)
    assert read_run(directory) is not None


def test_the_removal_commands_name_the_run_and_delete_nothing_by_themselves() -> None:
    commands = removal_commands("r1")
    assert any("forja-run/r1" in command for command in commands)
    assert commands[0] == "git worktree prune"
