"""A stage may commit some files first, on their own; the last commit is the one that ends it."""

from forja.core.idempotency import task_branch_name
from forja.orchestrator.workspace_git import CommitMessage
from tests.orchestrator.harness import RUN
from tests.orchestrator.test_workspace_contract import (  # noqa: F401 - the fixture and helpers
    MESSAGE,
    Backend,
    backend,
    go,
    start,
)

README = CommitMessage("docs(readme): fix the build line", "", "fake-cli 1.0", "0.0.0+abc")


def stage(b: Backend, files: dict[str, str], apart: tuple[str, ...]) -> str:
    ws = b.workspace
    go(ws.create_task_branch("t1"))
    go(ws.create_attempt_worktree("t1", "t1-a1"))
    worktree = ws.attempt_worktree("t1-a1")
    for name, text in files.items():
        (worktree / name).parent.mkdir(parents=True, exist_ok=True)
        (worktree / name).write_text(text, encoding="utf-8", newline="\n")
    go(ws.commit_stage("t1", "t1-d", "t1-a1", MESSAGE, apart, README))
    return task_branch_name(RUN, "t1")


def test_the_files_apart_are_committed_first_and_the_stage_ends_with_the_rest(
    backend: Backend,  # noqa: F811
) -> None:
    start(backend)

    branch = stage(backend, {"README.md": "# a", "docs/r.md": "record"}, ("README.md",))

    assert backend.subjects(branch) == [MESSAGE.subject, README.subject, "base"]
    assert backend.tip_trailers(branch)["Stage-Id"] == ["t1-d"]
    assert backend.read_tree(branch)["README.md"] == "# a"
    assert backend.read_tree(branch)["docs/r.md"] == "record"


def test_when_only_the_files_apart_changed_there_is_one_commit_and_it_ends_the_stage(
    backend: Backend,  # noqa: F811
) -> None:
    start(backend)

    branch = stage(backend, {"README.md": "# a"}, ("README.md",))

    assert backend.subjects(branch) == [MESSAGE.subject, "base"]
    assert backend.tip_trailers(branch)["Stage-Id"] == ["t1-d"]


def test_without_files_apart_the_stage_is_one_commit(backend: Backend) -> None:  # noqa: F811
    start(backend)

    branch = stage(backend, {"README.md": "# a", "docs/r.md": "record"}, ())

    assert backend.subjects(branch) == [MESSAGE.subject, "base"]
