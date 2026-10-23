"""Gate 6: the command plan of an end-to-end run, with the network turned off as far as Forja can.

An adapter has no tool of its own for E2E. The repository declares the command line (the ``e2e``
entry of ``[adapters.<language>.commands]``); the adapter's test plan supplies the directory, the
environment and the interpreter, and reads the output as it reads any test run. On top of that the
process gets the trap as its proxy and the offline switches the package managers honour.
"""

import dataclasses
from collections.abc import Mapping
from urllib.parse import urlsplit

from forja.core.adapters import (
    CommandPlan,
    LanguageAdapter,
    NotSupported,
    Operation,
    OperationRequest,
    plan_with_override,
)

LOOPBACK = "localhost,127.0.0.1,::1"
# measured against the real clients on 23/10 (docs\plano-gate-6.md, "Leitura do passo 0")
OFFLINE = {"npm_config_offline": "true", "PIP_NO_INDEX": "1", "GOPROXY": "off"}
NODE_PROXY = {"NODE_USE_ENV_PROXY": "1"}  # Node ignores the proxy variables without it
JAVA_OPTIONS = "JAVA_TOOL_OPTIONS"


def e2e_environment(proxy: str, host_env: Mapping[str, str]) -> dict[str, str]:
    """The variables that send a client's traffic to the trap at ``proxy`` (``http://host:port``).

    The JVM only honours its own properties, so they go in ``JAVA_TOOL_OPTIONS``, after whatever
    the user already set there.
    """
    address = urlsplit(proxy)
    host, port = address.hostname or "", address.port
    if not host or port is None:
        raise ValueError(f"not a proxy address: {proxy!r}")
    environment = {}
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"):
        environment[name] = proxy
        environment[name.lower()] = proxy
    environment["NO_PROXY"] = environment["no_proxy"] = LOOPBACK
    java = (
        f"-Dhttp.proxyHost={host} -Dhttp.proxyPort={port} "
        f"-Dhttps.proxyHost={host} -Dhttps.proxyPort={port} "
        "-Dhttp.nonProxyHosts=localhost|127.0.0.1"
    )
    inherited = host_env.get(JAVA_OPTIONS, "").strip()
    environment[JAVA_OPTIONS] = f"{inherited} {java}" if inherited else java
    return {**OFFLINE, **NODE_PROXY, **environment}


def e2e_plan(
    adapter: LanguageAdapter,
    request: OperationRequest,
    declared: tuple[str, ...] | None,
    proxy: str,
    host_env: Mapping[str, str],
) -> CommandPlan | NotSupported:
    """The plan to run ``declared`` as this adapter's E2E, or why there is none.

    ``declared`` is the repository's command line, or ``None`` when it did not declare one:
    Forja invents no default.
    """
    if declared is None:
        return NotSupported("e2e", "the repository declares no e2e command")
    plan = plan_with_override(
        adapter, Operation.TEST, request, {adapter.language: {"test": declared}}
    )
    if isinstance(plan, NotSupported):
        return NotSupported("e2e", plan.reason or plan.what)
    environment = {**plan.env_set, **e2e_environment(proxy, host_env)}
    return dataclasses.replace(plan, env_set=environment)
