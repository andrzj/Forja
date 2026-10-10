import asyncio
from pathlib import Path

import pytest

from forja.core.locking import git_is_running, remove_orphan_index_locks
from forja.core.process import running_process_names
from tests.core.idempotency.conftest import Repo
from tests.core.locking.support import age


def lock_in(repo: Repo) -> Path:
    path = repo.path / ".git" / "index.lock"
    path.write_text("")
    return path


def run(repo: Repo, **kwargs):  # type: ignore[no-untyped-def]
    return asyncio.run(remove_orphan_index_locks(repo.git, **kwargs))


def test_an_old_lock_with_no_git_running_is_removed(repo: Repo) -> None:
    path = lock_in(repo)
    age(path, 120)

    report = run(repo, git_running=lambda: False)

    assert [p.resolve() for p in report.removed] == [path.resolve()]
    assert report.kept == ()
    assert not path.exists()


def test_a_young_lock_may_belong_to_a_live_command_and_is_kept(repo: Repo) -> None:
    path = lock_in(repo)

    report = run(repo, git_running=lambda: False)

    assert report.removed == ()
    assert "only" in report.kept[0][1] and path.exists()


def test_an_old_lock_is_kept_while_any_git_process_runs(repo: Repo) -> None:
    path = lock_in(repo)
    age(path, 120)

    report = run(repo, git_running=lambda: True)

    assert report.removed == () and path.exists()
    assert report.kept[0][1] == "a git process is running"


def test_the_age_limit_is_adjustable(repo: Repo) -> None:
    path = lock_in(repo)
    age(path, 10)

    assert run(repo, min_age=5, git_running=lambda: False).removed != ()
    assert not path.exists()


def test_locks_of_linked_worktrees_are_handled_too(repo: Repo, tmp_path: Path) -> None:
    worktree = tmp_path / "wt"
    repo.sh("worktree", "add", "--detach", str(worktree))
    (admin,) = (repo.path / ".git" / "worktrees").iterdir()
    path = admin / "index.lock"
    path.write_text("")
    age(path, 120)

    report = run(repo, git_running=lambda: False)

    assert len(report.removed) == 1 and not path.exists()


def test_nothing_to_do_does_not_even_look_at_the_processes(repo: Repo) -> None:
    def must_not_be_called() -> bool:
        raise AssertionError("looked at the processes for nothing")

    report = run(repo, git_running=must_not_be_called)

    assert report.removed == () and report.kept == ()


def test_a_lock_that_cannot_be_removed_is_reported_not_raised(
    repo: Repo, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = lock_in(repo)
    age(path, 120)

    def refuse(self: Path, *args: object, **kwargs: object) -> None:
        raise PermissionError("in use")

    monkeypatch.setattr(Path, "unlink", refuse)

    report = run(repo, git_running=lambda: False)

    assert report.removed == () and "could not be removed" in report.kept[0][1]


def test_the_real_process_list_includes_this_process_and_no_invented_names() -> None:
    names = running_process_names()

    assert any(name.startswith("python") for name in names)
    assert "forja-no-such-program" not in names
    assert all(name == name.lower() for name in names)
    assert isinstance(git_is_running(), bool)
