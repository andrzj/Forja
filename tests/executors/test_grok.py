"""The Grok Build adapter: what it asks of the CLI and how it reads what comes back.

The lines follow the line shapes of ``headless/reducer/acp.rs`` and the tool inputs of the open
source of the CLI; no stream was recorded from the CLI itself (none is installed here). Run it
live to check them against a real one.
"""

import json
from pathlib import Path

from forja.core.adapters.executor import (
    AGENT_DIR,
    AgentRequest,
    CommandActivity,
    ErrorActivity,
    FileEditActivity,
    FileReadActivity,
    RolePermissions,
    TextActivity,
    UsageActivity,
)
from forja.core.artifacts.models import Producer
from forja.executors import GrokAdapter
from forja.executors.grok import CONFIG_FILE, HOME_DIR

adapter = GrokAdapter()


def line(**data: object) -> str:
    return json.dumps(data)


def tool(name: str, raw: object, kind: str = "other") -> str:
    return line(
        type="tool_call", toolCallId="1", title=name, kind=kind, status="pending",
        toolName=name, rawInput=raw, content=[], locations=[],
    )  # fmt: skip


def plan(tmp_path: Path, **permissions: object):  # type: ignore[no-untyped-def]
    allowed = RolePermissions(**{"can_edit_files": True, **permissions})  # type: ignore[arg-type]
    request = AgentRequest(Producer.IMPLEMENTER, tmp_path / "package.md", tmp_path, allowed)
    setup = adapter.permission_setup(Producer.IMPLEMENTER, allowed)
    return adapter.plan_invocation(request, setup, Path("/bin/grok"))


def config_of(**permissions: object) -> str:
    allowed = RolePermissions(**{"can_edit_files": True, **permissions})  # type: ignore[arg-type]
    setup = adapter.permission_setup(Producer.IMPLEMENTER, allowed)
    return setup.files[f"{HOME_DIR}/{CONFIG_FILE}"].decode()


# -- the invocation --------------------------------------------------------------------------------


def test_the_package_is_the_prompt_file_and_never_an_argument_or_stdin(tmp_path: Path) -> None:
    result = plan(tmp_path)

    assert result.argv[-2:] == ("--prompt-file", str(tmp_path / "package.md"))
    assert "-p" not in result.argv
    assert result.stdin_file is None
    assert result.cwd == tmp_path


def test_the_output_is_the_stream_and_the_features_that_reach_out_are_off(tmp_path: Path) -> None:
    argv = plan(tmp_path).argv

    assert argv[argv.index("--output-format") + 1] == "streaming-json"
    assert argv[argv.index("--cwd") + 1] == str(tmp_path)
    assert {"--no-subagents", "--no-plan", "--no-memory", "--disable-web-search"} <= set(argv)
    assert "--no-auto-update" in argv
    assert "--trust" not in argv


def test_what_is_not_allowed_is_denied_without_asking(tmp_path: Path) -> None:
    argv = plan(tmp_path).argv

    assert argv[argv.index("--permission-mode") + 1] == "dontAsk"
    assert "--always-approve" not in argv
    assert "--yolo" not in argv


def test_the_home_is_the_one_forja_wrote_and_other_tools_hooks_and_mcps_are_off(
    tmp_path: Path,
) -> None:
    env = plan(tmp_path).env_set

    assert env["GROK_HOME"] == str(tmp_path / AGENT_DIR / HOME_DIR)
    for name in ("CLAUDE_MCPS", "CLAUDE_HOOKS", "CURSOR_MCPS", "CURSOR_HOOKS"):
        assert env[f"GROK_{name}_ENABLED"] == "0"


def test_only_the_api_key_of_the_cli_is_passed_on(tmp_path: Path) -> None:
    allow = plan(tmp_path).env_allow

    assert "XAI_API_KEY" in allow
    assert "OPENAI_API_KEY" not in allow


# -- the permissions -------------------------------------------------------------------------------


def test_a_role_that_edits_gets_the_workspace_profile_and_the_edit_rule(tmp_path: Path) -> None:
    argv = plan(tmp_path).argv

    assert argv[argv.index("--sandbox") + 1] == "workspace"
    assert '"Edit"' in config_of()


def test_a_role_that_does_not_edit_gets_the_read_only_profile_and_no_edit_rule(
    tmp_path: Path,
) -> None:
    argv = plan(tmp_path, can_edit_files=False).argv

    assert argv[argv.index("--sandbox") + 1] == "read-only"
    assert '"Edit"' not in config_of(can_edit_files=False)


def test_a_role_without_commands_has_no_bash_rule() -> None:
    assert "Bash" not in config_of()


def test_each_command_is_an_allow_rule_with_its_parentheses_escaped() -> None:
    config = config_of(allowed_commands=("pytest -q", "echo (x)"))

    assert '"Bash(pytest -q)"' in config
    assert '"Bash(echo \\\\(x\\\\))"' in config


def test_the_web_and_mcp_are_denied() -> None:
    config = config_of()

    assert config.splitlines()[2] == 'deny = ["WebFetch", "WebSearch", "MCPTool"]'


# -- reading the stream ----------------------------------------------------------------------------


def test_the_message_is_text() -> None:
    assert adapter.parse_event(line(type="text", data="ok")) == TextActivity("ok")
    assert adapter.parse_event(line(type="text", data="  ")) is None


def test_a_read_a_replace_a_write_and_a_command_are_seen() -> None:
    read = tool("read_file", {"target_file": "src\\a.py"}, "read")
    replace = tool(
        "search_replace",
        {"file_path": "a.py", "old_string": "x", "new_string": "y\nz\n"},
        "edit",
    )
    write = tool("write", {"file_path": "b.txt", "content": "x\ny\n"}, "edit")
    command = tool("bash", {"command": "pytest -q"}, "execute")

    assert adapter.parse_event(read) == FileReadActivity("src/a.py")
    assert adapter.parse_event(replace) == FileEditActivity("a.py", 2, 1)
    assert adapter.parse_event(write) == FileEditActivity("b.txt", 2, 0)
    assert adapter.parse_event(command) == CommandActivity("pytest -q")


def test_a_call_that_has_no_arguments_yet_is_nothing() -> None:
    assert adapter.parse_event(tool("read_file", None)) is None
    assert adapter.parse_event(tool("bash", {})) is None


def test_the_update_of_a_call_is_not_counted_twice() -> None:
    event = line(type="tool_call_update", toolCallId="1", status="completed", rawOutput=None)

    assert adapter.parse_event(event) is None


def test_the_tool_of_another_kind_is_nothing() -> None:
    assert adapter.parse_event(tool("grep", {"pattern": "x"}, "search")) is None


def test_the_end_reports_the_use_without_the_cache() -> None:
    event = line(
        type="end", stopReason="end_turn", sessionId="s", requestId="r",
        usage={"input_tokens": 10, "output_tokens": 4, "cache_read_input_tokens": 90},
    )  # fmt: skip

    assert adapter.parse_event(event) == UsageActivity(10, 4)


def test_an_end_without_usage_reports_an_unknown_use() -> None:
    event = line(type="end", stopReason="end_turn", sessionId="s", requestId="r")

    assert adapter.parse_event(event) == UsageActivity()


def test_the_per_response_usage_line_is_not_counted() -> None:
    event = line(type="usage", usage={"input_tokens": 1, "output_tokens": 1})

    assert adapter.parse_event(event) is None


def test_an_end_for_another_reason_than_the_end_of_the_turn_is_an_error() -> None:
    seen = adapter.parse_event(line(type="end", stopReason="refusal", sessionId="s", requestId="r"))

    assert isinstance(seen, ErrorActivity)
    assert "refusal" in seen.message


def test_an_error_line_is_an_error() -> None:
    seen = adapter.parse_event(line(type="error", message="not signed in"))

    assert isinstance(seen, ErrorActivity)
    assert seen.message == "not signed in"


def test_the_maximum_of_turns_is_an_error() -> None:
    assert isinstance(adapter.parse_event(line(type="max_turns_reached")), ErrorActivity)


def test_what_is_not_an_event_is_nothing() -> None:
    assert adapter.parse_event("not json") is None
    assert adapter.parse_event("[1]") is None
    assert adapter.parse_event(line(type="thought", data="hm")) is None
    assert adapter.parse_event(line(type="plan", entries=[])) is None
