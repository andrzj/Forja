import os
import stat
import sys
from pathlib import Path

import pytest

from forja.core.adapters import (
    AGENT_DIR,
    AgentRequest,
    CommandActivity,
    DiscoverySpec,
    ErrorActivity,
    ErrorKind,
    ExecutorNotFound,
    FileEditActivity,
    FileReadActivity,
    PermissionSetup,
    ProbeTask,
    RolePermissions,
    Source,
    TemplateExecutorAdapter,
    TextActivity,
    UsageActivity,
    check_probe,
    environment_variable,
    find_executors,
    meets_minimum,
    version_tuple,
)
from forja.core.artifacts.models import Producer
from tests.core.adapters.fakes import FakeExecutorAdapter

ADAPTER = FakeExecutorAdapter()
PROBE = ProbeTask("p", "hello.txt", "hello", frozenset({"TextActivity"}))


def make_executable(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


# -- versions ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2.1.10", (2, 1, 10)),
        ("v3.0", (3, 0)),
        ("claude 1.2.3 (build 9)", (1, 2, 3)),
        ("", ()),
        ("abc", ()),
    ],
)
def test_versions_are_read_as_numbers_not_text(text: str, expected: tuple[int, ...]) -> None:
    assert version_tuple(text) == expected


def test_versions_compare_numerically() -> None:
    assert meets_minimum("2.1.10", "2.1.9")
    assert meets_minimum("2.0", "2.0.0") and meets_minimum("2.0.0", "2.0")  # same version
    assert not meets_minimum("1.2", "1.2.1")
    assert meets_minimum("1.2.0", "1.2")
    assert not meets_minimum("1.1.9", "1.2")
    assert not meets_minimum("not a version", "1.0")
    assert not meets_minimum("not a version", "0")  # an unreadable version never qualifies
    assert meets_minimum("0.0.1", "0")


# -- choosing the executable -------------------------------------------------------------------


def test_the_variable_name_comes_from_the_adapter_name() -> None:
    assert environment_variable("fake-agent") == "FORJA_EXECUTOR_FAKE_AGENT"
    assert environment_variable("Claude Code") == "FORJA_EXECUTOR_CLAUDE_CODE"


def test_precedence_is_explicit_then_variable_then_user_config_then_discovery(
    tmp_path: Path,
) -> None:
    explicit = make_executable(tmp_path / "a" / "explicit")
    by_variable = make_executable(tmp_path / "b" / "variable")
    by_config = make_executable(tmp_path / "c" / "config")
    on_path = make_executable(tmp_path / "d" / "fake-agent")
    env = {"PATH": str(on_path.parent), "FORJA_EXECUTOR_FAKE_AGENT": str(by_variable)}
    config = {"fake-agent": str(by_config)}

    def pick(**kwargs: object) -> tuple[Path, Source]:
        (choice,) = find_executors(ADAPTER, **kwargs)  # type: ignore[arg-type]
        return choice.path, choice.source

    assert pick(explicit=explicit, environ=env, user_config=config) == (explicit, Source.EXPLICIT)
    assert pick(environ=env, user_config=config) == (by_variable, Source.ENVIRONMENT)
    assert pick(environ={"PATH": env["PATH"]}, user_config=config) == (
        by_config,
        Source.USER_CONFIG,
    )
    assert pick(environ={"PATH": env["PATH"]}) == (on_path, Source.DISCOVERY)


@pytest.mark.parametrize("where", ["explicit", "variable", "config"])
def test_a_path_given_by_name_that_does_not_exist_is_an_error_not_a_fallback(
    tmp_path: Path, where: str
) -> None:
    real = make_executable(tmp_path / "bin" / "fake-agent")
    ghost = tmp_path / "ghost"
    env = {"PATH": str(real.parent)}
    kwargs: dict[str, object] = {"environ": env}
    source = {
        "explicit": Source.EXPLICIT,
        "variable": Source.ENVIRONMENT,
        "config": Source.USER_CONFIG,
    }
    if where == "explicit":
        kwargs["explicit"] = ghost
    elif where == "variable":
        kwargs["environ"] = {**env, "FORJA_EXECUTOR_FAKE_AGENT": str(ghost)}
    else:
        kwargs["user_config"] = {"fake-agent": str(ghost)}

    with pytest.raises(ExecutorNotFound) as info:
        find_executors(ADAPTER, **kwargs)  # type: ignore[arg-type]

    assert info.value.source is source[where] and info.value.path == ghost


def test_discovery_returns_every_installation_in_path_order_without_duplicates(
    tmp_path: Path,
) -> None:
    first = make_executable(tmp_path / "one" / "fake-agent")
    second = make_executable(tmp_path / "two" / "fake-agent")
    path = os.pathsep.join(str(p.parent) for p in (first, second, first))

    found = find_executors(ADAPTER, environ={"PATH": path})

    assert [c.path for c in found] == [first, second]
    assert {c.source for c in found} == {Source.DISCOVERY}


def test_nothing_found_is_an_empty_list_not_an_error(tmp_path: Path) -> None:
    assert find_executors(ADAPTER, environ={"PATH": str(tmp_path)}) == []
    assert find_executors(ADAPTER, environ={}) == []


def test_extra_locations_are_searched_with_variables_expanded(tmp_path: Path) -> None:
    installed = make_executable(tmp_path / "tools" / "bin" / "agent-x")
    adapter = TemplateExecutorAdapter(
        "x",
        DiscoverySpec(("agent-x",), extra_locations=("${TOOLS_HOME}/bin",)),
        ("{executable}", "{package}"),
        PROBE,
    )

    found = find_executors(adapter, environ={"PATH": "", "TOOLS_HOME": str(tmp_path / "tools")})

    assert [c.path for c in found] == [installed]


@pytest.mark.skipif(sys.platform != "win32", reason="PATHEXT is a Windows idea")
def test_on_windows_cmd_shims_are_found_by_their_bare_name(tmp_path: Path) -> None:
    shim = tmp_path / "bin" / "fake-agent.cmd"
    shim.parent.mkdir()
    shim.write_text("@echo off")

    found = find_executors(ADAPTER, environ={"PATH": str(shim.parent), "PATHEXT": ".EXE;.CMD"})

    assert [c.path.name.lower() for c in found] == ["fake-agent.cmd"]


def test_a_discovery_spec_needs_a_name_and_a_one_group_pattern() -> None:
    with pytest.raises(ValueError, match="executable name"):
        DiscoverySpec(())
    with pytest.raises(ValueError, match="capture group"):
        DiscoverySpec(("x",), version_pattern=r"\d+")


# -- the proof of life -------------------------------------------------------------------------


def test_the_proof_passes_when_the_file_and_the_events_are_there(tmp_path: Path) -> None:
    (tmp_path / "hello.txt").write_text("hello\n")

    assert check_probe(PROBE, tmp_path, [TextActivity("done")]) == []


def test_the_proof_names_each_thing_that_is_wrong(tmp_path: Path) -> None:
    assert check_probe(PROBE, tmp_path, []) == [
        "the CLI did not create hello.txt",
        "no TextActivity event was readable from the output",
    ]
    (tmp_path / "hello.txt").write_text("goodbye")
    problems = check_probe(
        PROBE, tmp_path, [TextActivity("x"), ErrorActivity("no auth", ErrorKind.BLOCKING)]
    )
    assert problems == [
        "hello.txt does not have the expected content",
        "the CLI reported an error: no auth",
    ]


# -- permissions and invocation ----------------------------------------------------------------


def test_permission_files_must_stay_inside_the_reserved_directory() -> None:
    PermissionSetup({"settings.json": b"{}", "sub/rules.json": b"{}"})
    for bad in ("../outside", "/abs", "C:evil", "a/../../b", ""):
        with pytest.raises(ValueError, match=AGENT_DIR):
            PermissionSetup({bad: b""})


def test_forja_is_not_an_agent_role(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="not an agent role"):
        AgentRequest(Producer.FORJA, tmp_path / "p.md", tmp_path, RolePermissions(False))


def test_the_package_is_delivered_by_file_and_the_roles_permissions_are_applied(
    tmp_path: Path,
) -> None:
    package = tmp_path / "package.md"
    permissions = RolePermissions(True, ("forja agente testar",))
    request = AgentRequest(Producer.IMPLEMENTER, package, tmp_path, permissions)
    setup = ADAPTER.permission_setup(Producer.IMPLEMENTER, permissions)

    executable = Path("/opt/fake-agent")
    plan = ADAPTER.plan_invocation(request, setup, executable)

    assert plan.argv[:3] == (str(executable), "--prompt-file", str(package))
    assert plan.argv[3:] == ("--settings", f"{AGENT_DIR}/settings.json")
    assert plan.env_allow == {"FAKE_API_KEY", "FAKE_BASE_URL"}
    assert b"forja agente testar" in setup.files["settings.json"]


# -- reading what the agent does ---------------------------------------------------------------


def test_events_become_typed_activity() -> None:
    parse = ADAPTER.parse_event

    assert parse('{"type":"text","text":"thinking"}') == TextActivity("thinking")
    assert parse('{"type":"read","path":"src/a.py"}') == FileReadActivity("src/a.py")
    assert parse('{"type":"edit","path":"src/a.py","added":3,"removed":1}') == FileEditActivity(
        "src/a.py", 3, 1
    )
    assert parse(
        '{"type":"command","command":"forja agente testar","exit_code":0}'
    ) == CommandActivity("forja agente testar", 0)
    assert parse('{"type":"usage","input_tokens":120,"output_tokens":30}') == UsageActivity(120, 30)
    assert parse('{"type":"error","message":"slow down","kind":"transient"}') == ErrorActivity(
        "slow down", ErrorKind.TRANSIENT
    )


def test_lines_that_are_not_events_are_ignored_not_fatal() -> None:
    for line in (
        "",
        "plain text",
        "{",
        "[]",
        "null",
        '{"type":"mystery"}',
        '{"type":"error","message":"x","kind":"odd"}',
    ):
        assert ADAPTER.parse_event(line) is None


def test_bad_numbers_in_an_event_do_not_become_garbage_counts() -> None:
    event = ADAPTER.parse_event('{"type":"edit","path":"a.py","added":"many","removed":-4}')

    assert event == FileEditActivity("a.py", 0, 0)


# -- a CLI described only by a template --------------------------------------------------------


def template(**changes: object) -> TemplateExecutorAdapter:
    fields: dict[str, object] = {
        "name": "generic",
        "discovery": DiscoverySpec(("generic-agent",)),
        "argv_template": ("{executable}", "run", "--role", "{role}", "--file", "{package}"),
        "probe": PROBE,
    }
    fields.update(changes)
    return TemplateExecutorAdapter(**fields)  # type: ignore[arg-type]


def test_placeholders_are_filled_from_the_request(tmp_path: Path) -> None:
    adapter = template(env_allow=frozenset({"GENERIC_KEY"}))
    request = AgentRequest(Producer.TEST_AUTHOR, tmp_path / "p.md", tmp_path, RolePermissions(True))
    executable = Path("/bin/generic-agent")

    plan = adapter.plan_invocation(
        request,
        adapter.permission_setup(Producer.TEST_AUTHOR, RolePermissions(True)),
        executable,
    )

    assert plan.argv == (
        str(executable),
        "run",
        "--role",
        "test_author",
        "--file",
        str(tmp_path / "p.md"),
    )
    assert plan.cwd == tmp_path and plan.stdin_file is None
    assert plan.env_allow == {"GENERIC_KEY"}


def test_the_package_can_be_piped_instead(tmp_path: Path) -> None:
    adapter = template(argv_template=("{executable}", "--stdin"), package_via_stdin=True)
    request = AgentRequest(Producer.IMPLEMENTER, tmp_path / "p.md", tmp_path, RolePermissions(True))

    plan = adapter.plan_invocation(request, PermissionSetup({}), Path("agent"))

    assert plan.argv == ("agent", "--stdin") and plan.stdin_file == tmp_path / "p.md"


def test_a_template_must_deliver_the_package_and_use_known_placeholders() -> None:
    with pytest.raises(ValueError, match="deliver the package"):
        template(argv_template=("{executable}", "run"))
    with pytest.raises(ValueError, match="unknown placeholders"):
        template(argv_template=("{executable}", "{package}", "{secret}"))
    with pytest.raises(ValueError, match="empty"):
        template(argv_template=())


def test_a_generic_cli_cannot_enforce_role_permissions_and_says_so(tmp_path: Path) -> None:
    adapter = template()

    assert adapter.enforces_permissions is False
    assert adapter.permission_setup(
        Producer.ARCHAEOLOGIST, RolePermissions(False)
    ) == PermissionSetup({})
    assert FakeExecutorAdapter.enforces_permissions is True


def test_a_generic_cli_shows_each_output_line_as_text() -> None:
    adapter = template()

    assert adapter.parse_event("working on it") == TextActivity("working on it")
    assert adapter.parse_event("   ") is None
