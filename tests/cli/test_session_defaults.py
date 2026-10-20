"""What a session assumes when the caller says nothing."""

import inspect
from pathlib import Path

import pytest

from forja.cli import session as session_module
from forja.cli.session import new_config, open_session, repo_python


def test_the_agent_runs_tests_unless_the_caller_says_otherwise() -> None:
    config = new_config(
        repo=Path("r"),
        base_commit="a" * 40,
        executor_name="claude-code",
        executor_path=Path("claude"),
        executor_version="2.0.0",
        tokens=1000,
    )

    assert config.agent_runs_tests is True


def test_a_session_is_interactive_unless_the_caller_says_otherwise() -> None:
    assert inspect.signature(open_session).parameters["interactive"].default is True


def test_python3_is_the_interpreter_when_only_it_is_on_the_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    found = tmp_path / "bin" / "python3"
    monkeypatch.setattr(
        session_module, "locate_in_path", lambda name: found if name == "python3" else None
    )

    assert repo_python(tmp_path) == (str(found),)
