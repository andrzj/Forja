"""The E2E plan: the repository's command, the adapter's setting, and the trap as the way out."""

from pathlib import Path

import pytest

from forja.checks.e2e_plan import LOOPBACK, e2e_environment, e2e_plan
from forja.core.adapters import CommandPlan, NotSupported, Operation, OperationRequest
from tests.core.adapters.fakes import FakeLanguageAdapter

PROXY = "http://127.0.0.1:5555"


class Refusing(FakeLanguageAdapter):
    def plan(self, operation: Operation, request: OperationRequest) -> CommandPlan | NotSupported:
        return NotSupported(operation.value, "no tests here")


def _request(tmp_path: Path) -> OperationRequest:
    return OperationRequest(root=tmp_path)


def test_without_a_declared_command_there_is_no_plan(tmp_path: Path) -> None:
    plan = e2e_plan(FakeLanguageAdapter(), _request(tmp_path), None, PROXY, {})
    assert plan == NotSupported("e2e", "the repository declares no e2e command")


def test_the_adapter_that_cannot_run_tests_gives_no_plan(tmp_path: Path) -> None:
    plan = e2e_plan(Refusing(), _request(tmp_path), ("make", "e2e"), PROXY, {})
    assert plan == NotSupported("e2e", "no tests here")


def test_the_declared_command_replaces_the_test_command_and_keeps_the_rest(tmp_path: Path) -> None:
    plan = e2e_plan(FakeLanguageAdapter(), _request(tmp_path), ("make", "e2e"), PROXY, {})
    assert isinstance(plan, CommandPlan)
    assert plan.argv == ("make", "e2e")
    assert plan.cwd == tmp_path
    assert plan.env_set["NO_COLOR"] == "1"  # the adapter's own setting survives
    assert plan.config_files == ("pyproject.toml",)


def test_every_proxy_variable_points_at_the_trap_in_both_cases(tmp_path: Path) -> None:
    plan = e2e_plan(FakeLanguageAdapter(), _request(tmp_path), ("make", "e2e"), PROXY, {})
    assert isinstance(plan, CommandPlan)
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"):
        assert plan.env_set[name] == PROXY
        assert plan.env_set[name.lower()] == PROXY
    assert plan.env_set["NO_PROXY"] == plan.env_set["no_proxy"] == LOOPBACK


def test_the_clients_that_ignore_the_proxy_variables_are_told_in_their_own_way() -> None:
    environment = e2e_environment(PROXY, {})
    assert environment["NODE_USE_ENV_PROXY"] == "1"
    options = environment["JAVA_TOOL_OPTIONS"]
    for part in (
        "-Dhttp.proxyHost=127.0.0.1",
        "-Dhttp.proxyPort=5555",
        "-Dhttps.proxyHost=127.0.0.1",
        "-Dhttps.proxyPort=5555",
        "-Dhttp.nonProxyHosts=localhost|127.0.0.1",
    ):
        assert part in options.split()


def test_the_offline_switches_are_on() -> None:
    environment = e2e_environment(PROXY, {})
    assert environment["npm_config_offline"] == "true"
    assert environment["PIP_NO_INDEX"] == "1"
    assert environment["GOPROXY"] == "off"


def test_the_users_own_jvm_options_stay_and_come_first() -> None:
    environment = e2e_environment(PROXY, {"JAVA_TOOL_OPTIONS": " -Xmx512m "})
    assert environment["JAVA_TOOL_OPTIONS"].startswith("-Xmx512m -Dhttp.proxyHost=")


def test_the_trap_wins_over_a_proxy_the_adapter_set(tmp_path: Path) -> None:
    class Proxied(FakeLanguageAdapter):
        def plan(
            self, operation: Operation, request: OperationRequest
        ) -> CommandPlan | NotSupported:
            return CommandPlan(("x",), request.root, env_set={"HTTP_PROXY": "http://elsewhere:1"})

    plan = e2e_plan(Proxied(), _request(tmp_path), ("make", "e2e"), PROXY, {})
    assert isinstance(plan, CommandPlan)
    assert plan.env_set["HTTP_PROXY"] == PROXY


@pytest.mark.parametrize("proxy", ["", "127.0.0.1:5555", "http://127.0.0.1", "http://:80"])
def test_an_address_without_host_or_port_is_refused(proxy: str) -> None:
    with pytest.raises(ValueError, match="not a proxy address"):
        e2e_environment(proxy, {})
