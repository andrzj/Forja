"""The Gemini CLI adapter: what it asks of the CLI and how it reads what comes back.

The event lines follow the shapes in the CLI's source (``packages/core/src/output/types.ts``) and
its tool declarations; no stream was recorded from the CLI itself (none is logged in here). Run it
live to check them against a real one.
"""

import json
import tomllib
from pathlib import Path

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
from forja.executors import GeminiAdapter
from forja.executors.gemini import POLICY_FILE

adapter = GeminiAdapter()


def line(**data: object) -> str:
    return json.dumps({"timestamp": "2026-10-21T00:00:00Z", **data})


def plan(tmp_path: Path, **permissions: object):  # type: ignore[no-untyped-def]
    allowed = RolePermissions(**{"can_edit_files": True, **permissions})  # type: ignore[arg-type]
    request = AgentRequest(Producer.IMPLEMENTER, tmp_path / "package.md", tmp_path, allowed)
    setup = adapter.permission_setup(Producer.IMPLEMENTER, allowed)
    return adapter.plan_invocation(request, setup, Path("/bin/gemini"))


def rules_of(**permissions: object) -> list[dict[str, object]]:
    allowed = RolePermissions(**{"can_edit_files": True, **permissions})  # type: ignore[arg-type]
    setup = adapter.permission_setup(Producer.IMPLEMENTER, allowed)
    rules: list[dict[str, object]] = tomllib.loads(setup.files[POLICY_FILE].decode("utf-8"))["rule"]
    return rules


# -- the invocation --------------------------------------------------------------------------------


def test_the_package_goes_on_stdin_and_the_stream_is_json(tmp_path: Path) -> None:
    result = plan(tmp_path)

    assert result.argv[:2] == (str(Path("/bin/gemini")), "-p")
    assert result.argv[result.argv.index("--output-format") + 1] == "stream-json"
    assert result.stdin_file == tmp_path / "package.md"
    assert result.cwd == tmp_path


def test_nothing_is_approved_by_mode_and_no_project_mcp_server_connects(tmp_path: Path) -> None:
    argv = plan(tmp_path).argv

    assert argv[argv.index("--approval-mode") + 1] == "default"
    assert "--yolo" not in argv
    assert "--skip-trust" not in argv
    assert argv[argv.index("--allowed-mcp-server-names") + 1] == "forja-none"


def test_the_policy_file_is_the_one_the_command_names(tmp_path: Path) -> None:
    argv = plan(tmp_path).argv

    assert argv[argv.index("--policy") + 1] == f"{AGENT_DIR}/{POLICY_FILE}"


def test_only_the_cli_login_variables_are_passed_on(tmp_path: Path) -> None:
    result = plan(tmp_path)

    assert "GEMINI_API_KEY" in result.env_allow
    assert "OPENAI_API_KEY" not in result.env_allow
    assert result.env_set["GEMINI_CLI_TRUST_WORKSPACE"] == "true"


# -- the policy ------------------------------------------------------------------------------------


def test_a_role_that_edits_may_use_the_edit_tools() -> None:
    allowed = {rule["toolName"] for rule in rules_of() if rule["decision"] == "allow"}

    assert {"write_file", "replace", "read_file"} <= allowed


def test_a_role_that_does_not_edit_has_no_edit_tool() -> None:
    names = {rule["toolName"] for rule in rules_of(can_edit_files=False)}

    assert "write_file" not in names
    assert "replace" not in names
    assert "read_file" in names


def test_no_command_runs_unless_listed() -> None:
    assert "run_shell_command" not in {rule["toolName"] for rule in rules_of()}


def test_a_listed_command_matches_whole_and_nothing_else() -> None:
    import re

    [rule] = [r for r in rules_of(allowed_commands=("pytest -q",)) if r["toolName"] != "*"][-1:]
    pattern = re.compile(f'"command":"{rule["commandRegex"]}')

    assert pattern.search('"command":"pytest -q","is_background":false')
    assert not pattern.search('"command":"pytest -q; rm -rf x"')
    assert not pattern.search('"command":"echo hi; pytest -q"')


def test_the_command_is_escaped_as_json_would_show_it() -> None:
    import re

    rule = rules_of(allowed_commands=('echo "a"',))[-2]
    pattern = re.compile(f'"command":"{rule["commandRegex"]}')

    assert pattern.search(json.dumps({"command": 'echo "a"'}, separators=(",", ":"))[1:])


def test_a_deny_all_rule_ranks_below_every_allow() -> None:
    rules = rules_of(allowed_commands=("pytest -q",))
    deny = [r for r in rules if r["decision"] == "deny"]
    allow = [r for r in rules if r["decision"] == "allow"]

    assert [r["toolName"] for r in deny] == ["*"]
    assert all(deny[0]["priority"] < r["priority"] for r in allow)  # type: ignore[operator]


# -- reading the stream ----------------------------------------------------------------------------


def test_the_assistant_text_is_text() -> None:
    event = line(type="message", role="assistant", content="done", delta=True)

    assert adapter.parse_event(event) == TextActivity("done")


def test_the_prompt_echoed_back_is_not_text() -> None:
    assert adapter.parse_event(line(type="message", role="user", content="do")) is None


def test_a_write_is_a_file_edit_with_its_lines() -> None:
    event = line(
        type="tool_use", tool_name="write_file", tool_id="1",
        parameters={"file_path": "a\\b.py", "content": "x\ny\n"},
    )  # fmt: skip

    assert adapter.parse_event(event) == FileEditActivity("a/b.py", 2, 0)


def test_a_replace_counts_both_sides() -> None:
    event = line(
        type="tool_use", tool_name="replace", tool_id="1",
        parameters={"file_path": "a.py", "old_string": "x", "new_string": "y\nz"},
    )  # fmt: skip

    assert adapter.parse_event(event) == FileEditActivity("a.py", 2, 1)


def test_a_read_and_a_command() -> None:
    read = line(type="tool_use", tool_name="read_file", tool_id="1", parameters={"file_path": "a"})
    run = line(
        type="tool_use", tool_name="run_shell_command", tool_id="2", parameters={"command": "ls"}
    )

    assert adapter.parse_event(read) == FileReadActivity("a")
    assert adapter.parse_event(run) == CommandActivity("ls")


def test_a_tool_without_its_arguments_is_nothing() -> None:
    event = line(type="tool_use", tool_name="write_file", tool_id="1", parameters={})

    assert adapter.parse_event(event) is None


def test_the_cached_input_is_not_counted() -> None:
    event = line(
        type="result", status="success",
        stats={"input_tokens": 100, "cached": 30, "output_tokens": 7, "total_tokens": 107},
    )  # fmt: skip

    assert adapter.parse_event(event) == UsageActivity(70, 7)


def test_a_failed_result_is_an_error() -> None:
    event = line(
        type="result", status="error", error={"type": "Error", "message": "quota exceeded 429"}
    )

    seen = adapter.parse_event(event)

    assert isinstance(seen, ErrorActivity)
    assert seen.message == "quota exceeded 429"
    assert isinstance(seen.kind, ErrorKind)


def test_what_is_not_an_event_is_nothing() -> None:
    assert adapter.parse_event("not json") is None
    assert adapter.parse_event("[1]") is None
    assert adapter.parse_event(line(type="init", session_id="s", model="m")) is None
    assert adapter.parse_event(line(type="error", severity="warning", message="m")) is None
