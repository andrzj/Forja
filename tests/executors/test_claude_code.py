"""The Claude Code adapter: what it asks of the CLI and how it reads what comes back.

The authentication failure is a real stream recorded from the CLI (fixtures/). The shapes of the
tool calls follow the stream-json format the CLI documents; ``test_live.py`` checks them against
the real CLI whenever it is run with FORJA_LIVE=1.
"""

import json
from pathlib import Path

import pytest

from forja.core.adapters.executor import (
    AGENT_DIR,
    AgentRequest,
    CommandActivity,
    ErrorActivity,
    ErrorKind,
    FileEditActivity,
    FileReadActivity,
    RolePermissions,
    TextActivity,
    UsageActivity,
)
from forja.core.artifacts.models import Producer
from forja.executors import ClaudeCodeAdapter
from forja.executors.claude_code import classify_error

FIXTURE = Path(__file__).with_name("fixtures") / "claude_auth_failed.jsonl"
adapter = ClaudeCodeAdapter()


def line(**data: object) -> str:
    return json.dumps(data)


def assistant(*blocks: dict[str, object]) -> str:
    return line(type="assistant", message={"role": "assistant", "content": list(blocks)})


def tool(name: str, **arguments: object) -> dict[str, object]:
    return {"type": "tool_use", "id": "t1", "name": name, "input": arguments}


# -- the invocation --------------------------------------------------------------------------------


def request(tmp_path: Path, **permissions: object) -> AgentRequest:
    allowed = RolePermissions(**{"can_edit_files": True, **permissions})  # type: ignore[arg-type]
    return AgentRequest(Producer.IMPLEMENTER, tmp_path / "package.md", tmp_path, allowed)


def plan_of(tmp_path: Path, **permissions: object) -> tuple[str, ...]:
    asked = request(tmp_path, **permissions)
    setup = adapter.permission_setup(asked.role, asked.permissions)
    return adapter.plan_invocation(asked, setup, Path("/bin/claude")).argv


def test_the_package_goes_on_stdin_and_the_work_is_headless(tmp_path: Path) -> None:
    asked = request(tmp_path)
    setup = adapter.permission_setup(asked.role, asked.permissions)

    plan = adapter.plan_invocation(asked, setup, Path("/bin/claude"))

    assert plan.argv[:2] == (str(Path("/bin/claude")), "-p")
    assert plan.stdin_file == tmp_path / "package.md"
    assert plan.cwd == tmp_path
    assert plan.env_set == {"NO_COLOR": "1"}
    assert plan.argv[2:4] == ("--output-format", "stream-json")
    assert "--verbose" in plan.argv


def test_only_the_users_settings_are_read_and_hooks_are_off(tmp_path: Path) -> None:
    argv = plan_of(tmp_path)

    assert argv[argv.index("--setting-sources") + 1] == "user"
    assert argv[argv.index("--settings") + 1] == f"{AGENT_DIR}/claude-settings.json"
    for flag in ("--strict-mcp-config", "--disable-slash-commands", "--no-session-persistence"):
        assert flag in argv
    assert "--bare" not in argv  # it would refuse the login the user already made
    setup = adapter.permission_setup(Producer.IMPLEMENTER, RolePermissions(True))
    settings = json.loads(setup.files["claude-settings.json"])
    assert settings["disableAllHooks"] is True
    assert {"Read(../**)", "Edit(../**)", "Write(~/**)"} <= set(settings["permissions"]["deny"])


def test_an_editing_role_can_read_and_edit_but_not_run_commands(tmp_path: Path) -> None:
    argv = plan_of(tmp_path)

    assert argv[argv.index("--tools") + 1] == "Read,Glob,Grep,Edit,Write"
    assert argv[argv.index("--allowedTools") + 1] == "Read,Glob,Grep,Edit,Write"
    assert argv[argv.index("--permission-mode") + 1] == "dontAsk"


def test_a_reading_role_cannot_edit(tmp_path: Path) -> None:
    argv = plan_of(tmp_path, can_edit_files=False)

    assert argv[argv.index("--tools") + 1] == "Read,Glob,Grep"


def test_commands_are_allowed_only_as_the_role_names_them(tmp_path: Path) -> None:
    argv = plan_of(tmp_path, allowed_commands=("forja agente testar",))

    assert argv[argv.index("--tools") + 1].endswith(",Bash")
    assert argv[argv.index("--allowedTools") + 1].endswith(",Bash(forja agente testar *)")


def test_the_users_own_configuration_reaches_the_cli_but_a_hosts_does_not() -> None:
    names = adapter.env_allow

    assert {"ANTHROPIC_API_KEY", "ANTHROPIC_BASE_URL", "CLAUDE_CONFIG_DIR", "APPDATA"} <= names
    assert not any(name.startswith("CLAUDE_CODE_SESSION") for name in names)
    assert "CLAUDE_CODE_ENTRYPOINT" not in names


# -- reading the stream ----------------------------------------------------------------------------


def test_a_real_authentication_failure_blocks_the_run_with_the_clis_own_words() -> None:
    activities = [adapter.parse_event(text) for text in FIXTURE.read_text("utf-8").splitlines()]

    errors = [a for a in activities if isinstance(a, ErrorActivity)]
    assert len(errors) == 1  # the assistant line repeats it and is ignored
    assert errors[0].kind is ErrorKind.BLOCKING
    assert "OAuth session expired" in errors[0].message


def test_reading_and_editing_are_shown_with_the_lines_they_touch() -> None:
    assert adapter.parse_event(assistant(tool("Read", file_path="src\\a.py"))) == FileReadActivity(
        "src/a.py"
    )
    edit = tool("Edit", file_path="a.py", old_string="x\ny\n", new_string="z\n")
    assert adapter.parse_event(assistant(edit)) == FileEditActivity("a.py", 1, 2)
    write = tool("Write", file_path="b.py", content="1\n2\n3\n")
    assert adapter.parse_event(assistant(write)) == FileEditActivity("b.py", 3, 0)


def test_a_command_and_a_sentence_are_shown_as_they_are() -> None:
    assert adapter.parse_event(assistant(tool("Bash", command="ls"))) == CommandActivity("ls")
    said = assistant({"type": "text", "text": "I renamed it."})
    assert adapter.parse_event(said) == TextActivity("I renamed it.")


def test_the_first_thing_a_message_does_is_what_is_shown() -> None:
    mixed = assistant({"type": "text", "text": "  "}, tool("Read", file_path="a.py"))

    assert adapter.parse_event(mixed) == FileReadActivity("a.py")


def test_tokens_are_what_was_sent_and_written_and_not_what_the_cache_gave_back() -> None:
    usage = {
        "input_tokens": 10,
        "cache_creation_input_tokens": 5,
        "cache_read_input_tokens": 9000,
        "output_tokens": 7,
    }

    assert adapter.parse_event(line(type="result", is_error=False, usage=usage)) == UsageActivity(
        15, 7
    )


@pytest.mark.parametrize(
    "text",
    [
        "not json",
        "[]",
        line(type="system", subtype="init"),
        line(type="assistant", message={"content": "plain"}),
        assistant(tool("Read")),
        assistant(tool("Glob", pattern="*.py")),
        line(type="result", is_error=False),
        line(type="assistant", error="authentication_failed", message={"content": []}),
    ],
)
def test_what_is_not_activity_is_left_alone(text: str) -> None:
    assert adapter.parse_event(text) is None


# -- what a failure means --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("message", "status", "kind"),
    [
        ("anything", 401, ErrorKind.BLOCKING),
        ("anything", 403, ErrorKind.BLOCKING),
        ("anything", 429, ErrorKind.TRANSIENT),
        ("anything", 503, ErrorKind.TRANSIENT),
        ("Failed to authenticate: OAuth session expired", None, ErrorKind.BLOCKING),
        ("Your credit balance is too low", None, ErrorKind.BLOCKING),
        ("getaddrinfo ENOTFOUND api.example.com", None, ErrorKind.PERSISTENT),
        ("socket hang up", None, ErrorKind.TRANSIENT),
        ("overloaded", True, ErrorKind.TRANSIENT),
    ],
)
def test_a_failure_is_classified_by_status_first_and_by_its_words_after(
    message: str, status: object, kind: ErrorKind
) -> None:
    assert classify_error(message, status) is kind


def test_the_cli_is_found_by_name_and_has_a_minimum_version() -> None:
    assert adapter.discovery.executable_names == ("claude",)
    assert adapter.discovery.min_version == "2.0.0"
    assert adapter.enforces_permissions
