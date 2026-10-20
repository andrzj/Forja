"""The Codex adapter: what it asks of the CLI and how it reads what comes back.

The event lines follow the shapes in the CLI's source (``codex-rs/exec/src/exec_events.rs``) and
the sample stream of its non-interactive mode page; no stream was recorded from the CLI itself
(none is installed here). Run it live to check them against a real one.
"""

import json
from pathlib import Path

import pytest

from forja.core.adapters.executor import (
    AgentRequest,
    CommandActivity,
    ErrorActivity,
    ErrorKind,
    FileEditActivity,
    RolePermissions,
    TextActivity,
    UsageActivity,
)
from forja.core.artifacts.models import Producer
from forja.executors import CodexAdapter

adapter = CodexAdapter()


def line(**data: object) -> str:
    return json.dumps(data)


def completed(**item: object) -> str:
    return line(type="item.completed", item={"id": "item_1", **item})


def plan(tmp_path: Path, **permissions: object):  # type: ignore[no-untyped-def]
    allowed = RolePermissions(**{"can_edit_files": True, **permissions})  # type: ignore[arg-type]
    request = AgentRequest(Producer.IMPLEMENTER, tmp_path / "package.md", tmp_path, allowed)
    setup = adapter.permission_setup(Producer.IMPLEMENTER, allowed)
    return adapter.plan_invocation(request, setup, Path("/bin/codex"))


# -- the invocation --------------------------------------------------------------------------------


def test_the_prompt_comes_from_the_package_on_stdin(tmp_path: Path) -> None:
    result = plan(tmp_path)

    assert result.argv[:3] == (str(Path("/bin/codex")), "exec", "--json")
    assert result.argv[-1] == "-"
    assert result.stdin_file == tmp_path / "package.md"
    assert result.cwd == tmp_path


def test_nothing_of_the_repository_or_the_session_is_read_or_kept(tmp_path: Path) -> None:
    argv = plan(tmp_path).argv

    assert "--ephemeral" in argv
    assert "--ignore-rules" in argv
    assert "project_doc_max_bytes=0" in argv
    assert "features.hooks=false" in argv
    assert "sandbox_workspace_write.network_access=false" in argv
    assert "sandbox_workspace_write.writable_roots=[]" in argv


@pytest.mark.parametrize(("can_edit", "sandbox"), [(True, "workspace-write"), (False, "read-only")])
def test_the_sandbox_follows_what_the_role_may_do(
    tmp_path: Path, can_edit: bool, sandbox: str
) -> None:
    argv = plan(tmp_path, can_edit_files=can_edit).argv

    assert argv[argv.index("--sandbox") + 1] == sandbox


def test_the_limitation_on_commands_is_declared() -> None:
    assert adapter.enforces_permissions is False


def test_only_the_cli_own_variables_are_passed_on() -> None:
    assert {"CODEX_HOME", "CODEX_API_KEY"} <= adapter.env_allow
    assert not any(name.startswith(("ANTHROPIC_", "CLAUDE")) for name in adapter.env_allow)


# -- the events -----------------------------------------------------------------------------------


def test_a_message_of_the_agent_is_text() -> None:
    event = adapter.parse_event(completed(type="agent_message", text="Repo has docs."))

    assert event == TextActivity("Repo has docs.")


def test_a_command_carries_its_exit_code() -> None:
    event = adapter.parse_event(
        completed(type="command_execution", command="bash -lc ls", exit_code=1, status="failed")
    )

    assert event == CommandActivity("bash -lc ls", 1)


def test_a_command_still_running_has_no_exit_code() -> None:
    event = adapter.parse_event(completed(type="command_execution", command="ls", exit_code=None))

    assert event == CommandActivity("ls", None)


def test_a_file_change_names_the_file() -> None:
    event = adapter.parse_event(
        completed(
            type="file_change",
            status="completed",
            changes=[{"path": "src\\a.py", "kind": "update"}],
        )
    )

    assert event == FileEditActivity("src/a.py", 0, 0)


def test_a_file_change_that_failed_is_not_an_edit() -> None:
    event = adapter.parse_event(
        completed(type="file_change", status="failed", changes=[{"path": "a.py", "kind": "add"}])
    )

    assert event is None


def test_the_cached_input_is_not_counted() -> None:
    event = adapter.parse_event(
        line(
            type="turn.completed",
            usage={"input_tokens": 24763, "cached_input_tokens": 24448, "output_tokens": 122},
        )
    )

    assert event == UsageActivity(315, 122)


@pytest.mark.parametrize(
    ("message", "kind"),
    [
        ("unexpected status 401 Unauthorized", ErrorKind.BLOCKING),
        ("getaddrinfo ENOTFOUND api.openai.com", ErrorKind.PERSISTENT),
        ("stream disconnected", ErrorKind.TRANSIENT),
    ],
)
@pytest.mark.parametrize("shape", ["turn.failed", "error"])
def test_a_failure_is_an_error_of_the_kind_it_means(
    shape: str, message: str, kind: ErrorKind
) -> None:
    text = (
        line(type="turn.failed", error={"message": message})
        if shape == "turn.failed"
        else line(type="error", message=message)
    )

    assert adapter.parse_event(text) == ErrorActivity(message, kind)


@pytest.mark.parametrize(
    "text",
    [
        line(type="thread.started", thread_id="x"),
        line(type="turn.started"),
        line(type="item.started", item={"id": "i", "type": "command_execution", "command": "ls"}),
        completed(type="reasoning", text="thinking"),
        completed(type="agent_message", text="  "),
        line(type="turn.completed", usage="x"),
    ],
)
def test_what_says_nothing_to_forja_is_skipped(text: str) -> None:
    assert adapter.parse_event(text) is None
