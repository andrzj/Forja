"""What the agent is told: the task, the rules, the files it may change, and why it was rejected."""

from pathlib import Path

from forja.core.redaction import Redactor
from forja.orchestrator.agent_runner import _fence, build_package
from forja.orchestrator.ports import AttemptContext, TaskInfo

TOKEN = "ghp_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"


def context(tmp_path: Path, scope: tuple[str, ...], rejection: str | None = None) -> AttemptContext:
    (tmp_path / "src").mkdir(exist_ok=True)
    (tmp_path / "src" / "a.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    task = TaskInfo("t1", "t1-s", "reduce the complexity of f", scope, 3, 120)
    return AttemptContext(task, "t1-a1", tmp_path, rejection)


def package(tmp_path: Path, scope: tuple[str, ...] = ("src/a.py",), **more: str | None) -> str:
    return build_package(context(tmp_path, scope, **more), Redactor())


def test_the_package_names_the_task_the_scope_and_the_limits(tmp_path: Path) -> None:
    text = package(tmp_path)

    assert "reduce the complexity of f" in text
    assert "Only inside: `src/a.py`." in text
    assert "At most 3 files and 120 changed lines." in text


def test_the_package_tells_the_agent_what_it_cannot_do_and_how_to_declare_its_work(
    tmp_path: Path,
) -> None:
    text = package(tmp_path)

    assert "You cannot run commands" in text
    assert "Do not change tests" in text
    assert ".forja-agent/saida.json" in text
    assert '"change": "modified"' in text


def test_the_files_in_scope_are_in_the_package_as_they_are(tmp_path: Path) -> None:
    text = package(tmp_path)

    assert "### `src/a.py`\n\n```\ndef f():\n    return 1\n\n```" in text


def test_a_secret_in_a_file_never_reaches_the_package(tmp_path: Path) -> None:
    context(tmp_path, ("src/a.py",))
    (tmp_path / "src" / "a.py").write_text(f'KEY = "{TOKEN}"\n', encoding="utf-8")

    assert TOKEN not in package(tmp_path)


def test_a_sensitive_file_is_withheld_and_said_to_be(tmp_path: Path) -> None:
    context(tmp_path, ("src/a.py",))
    (tmp_path / ".env").write_text("A=1\n", encoding="utf-8")

    text = package(tmp_path, ("src/a.py", ".env"))

    assert "`.env` was withheld (sensitive_file)." in text
    assert "A=1" not in text


def test_a_directory_in_the_scope_is_named_and_not_pasted(tmp_path: Path) -> None:
    text = package(tmp_path, ("src",))

    assert "`src` is a directory: read the files you need from it." in text
    assert "return 1" not in text


def test_the_reason_for_the_last_rejection_is_in_the_package_only_when_there_was_one(
    tmp_path: Path,
) -> None:
    assert "previous attempt" not in package(tmp_path)

    text = package(tmp_path, rejection="lint: 2 new F401 violation(s) [src/a.py]")

    assert "## The previous attempt was rejected\n\nlint: 2 new F401 violation(s)" in text


def test_a_fence_is_longer_than_any_run_of_backticks_inside() -> None:
    assert _fence("plain") == "```"
    assert _fence("a ``` b") == "````"
    assert _fence("a ```` b") == "`````"
