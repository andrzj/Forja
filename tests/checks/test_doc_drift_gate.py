"""Gate 14 for drift: only the drift the task brought is rejected (the ratchet)."""

import asyncio
from pathlib import Path

import pytest

from forja.checks.doc_drift import Facts
from forja.checks.doc_drift_gate import MAX_TEXT_BYTES, Base, DocDriftCheck, read_repository
from forja.core.gates import Approved, GateInput, GateResult, Rejected
from tests.core.idempotency.conftest import Repo, repo  # noqa: F401 - re-exported as a fixture

OLD_README = "# sample\n\nSee `old_helper()` and `docs/gone.md` and `make ship`.\n"


def commit(repo: Repo, message: str) -> None:  # noqa: F811
    repo.sh("add", "-A")
    repo.sh("commit", "-m", message, "--trailer", "Task-Id: t1")


def write(repo: Repo, name: str, text: str) -> None:  # noqa: F811
    path = repo.path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def judge(repo: Repo, base: str) -> GateResult:  # noqa: F811
    def is_document(path: str) -> bool:
        return path.endswith(".md")

    async def run() -> GateResult:
        documents, facts = await read_repository(repo.git, repo.path, is_document, "docs/mudancas")
        check = DocDriftCheck(documents, facts, Base(repo.git, base))
        return await check.evaluate(GateInput(repo.path, "c" * 40, "t1", "t1-d", "t1-da1"))

    return asyncio.run(run())


def said(result: GateResult) -> list[str]:
    assert isinstance(result, Rejected)
    return [f.message for f in result.findings]


def test_drift_that_was_there_at_the_base_is_left_alone(repo: Repo) -> None:  # noqa: F811
    write(repo, "README.md", OLD_README)
    commit(repo, "docs: readme")
    base = repo.sh("rev-parse", "HEAD")
    write(repo, "src/mod.py", "def other():\n    pass\n")
    commit(repo, "refactor: other")

    assert isinstance(judge(repo, base), Approved)


def test_a_name_the_task_removed_is_new_drift(repo: Repo) -> None:  # noqa: F811
    write(repo, "src/mod.py", "def helper():\n    pass\n")
    write(repo, "README.md", "Use `helper()` from `src/mod.py` and `src/other.py`.\n")
    commit(repo, "feat: helper")
    base = repo.sh("rev-parse", "HEAD")
    write(repo, "src/mod.py", "def renamed():\n    pass\n")
    commit(repo, "refactor: rename")

    assert said(judge(repo, base)) == ["line 1 cites symbol `helper()` and helper is gone"]


def test_a_path_the_task_deleted_is_new_drift_and_one_missing_at_the_base_is_not(
    repo: Repo,  # noqa: F811
) -> None:
    write(repo, "src/a.py", "x = 1\n")
    write(repo, "README.md", "`src/a.py` and `src/never.py`\n")
    commit(repo, "feat: a")
    base = repo.sh("rev-parse", "HEAD")
    (repo.path / "src" / "a.py").unlink()
    commit(repo, "refactor: drop a")

    result = judge(repo, base)

    assert said(result) == ["line 1 cites path `src/a.py` and src/a.py is gone"]


def test_a_citation_the_documenter_just_wrote_is_new_even_if_nothing_ever_had_it(
    repo: Repo,  # noqa: F811
) -> None:
    write(repo, "README.md", "# sample\n")
    commit(repo, "docs: readme")
    base = repo.sh("rev-parse", "HEAD")
    write(repo, "README.md", "# sample\n\nCall `invented_name()`.\n")  # not committed yet

    assert said(judge(repo, base)) == [
        "line 3 cites symbol `invented_name()` and invented_name is gone"
    ]


def test_the_records_of_the_tasks_are_history_and_are_not_read(repo: Repo) -> None:  # noqa: F811
    base = repo.sh("rev-parse", "HEAD")
    write(repo, "docs/mudancas/t0.md", "removed `old_helper()`\n")

    assert isinstance(judge(repo, base), Approved)


def test_a_link_to_a_file_outside_the_worktree_adds_nothing_to_what_can_be_cited(
    repo: Repo,  # noqa: F811
    tmp_path: Path,
) -> None:
    outside = tmp_path / "outside.py"
    outside.write_text("def secret_name():\n    pass\n", encoding="utf-8")
    link = repo.path / "link.py"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        return
    base = repo.sh("rev-parse", "HEAD")
    write(repo, "README.md", "`secret_name()`\n")

    assert said(judge(repo, base)) == [
        "line 1 cites symbol `secret_name()` and secret_name is gone"
    ]


def read(repo: Repo) -> Facts:  # noqa: F811
    async def run() -> Facts:
        _, facts = await read_repository(
            repo.git, repo.path, lambda path: path.endswith(".md"), "docs/mudancas"
        )
        return facts

    return asyncio.run(run())


def test_a_makefile_and_a_package_json_below_the_root_are_read(repo: Repo) -> None:  # noqa: F811
    write(repo, "sub/Makefile", "build:\n\techo\n")
    write(repo, "web/package.json", '{"scripts": {"lint": "x"}}')
    write(repo, "data.json", '{"scripts": {"stray": "x"}}')
    facts = read(repo)
    assert "build" in facts.make_targets
    assert "lint" in facts.scripts
    assert "stray" not in facts.scripts


def test_a_file_of_exactly_the_size_limit_is_read_and_one_byte_more_is_not(
    repo: Repo,  # noqa: F811
) -> None:
    write(repo, "src/at_limit.py", "atlimitword" + " " * (MAX_TEXT_BYTES - 11))
    write(repo, "src/over_limit.py", "overlimitword" + " " * (MAX_TEXT_BYTES - 12))
    facts = read(repo)
    assert "atlimitword" in facts.words
    assert "overlimitword" not in facts.words


def test_a_link_is_not_read_as_a_file_of_the_repository(
    repo: Repo,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    write(repo, "src/real.py", "realword = 1\n")
    write(repo, "src/linked.py", "linkedword = 1\n")
    real = Path.is_symlink
    monkeypatch.setattr(Path, "is_symlink", lambda self: self.name == "linked.py" or real(self))
    facts = read(repo)
    assert "realword" in facts.words
    assert "linkedword" not in facts.words
    assert "src/linked.py" not in facts.files
