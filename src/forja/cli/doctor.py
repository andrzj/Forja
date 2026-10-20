"""``forja doctor``: everything the Forja needs, checked, and what to do for each thing missing.

The configuration of the agent CLI (login, model, gateway) is the person's and must be ready
before; the doctor proves it works with a small task and says so when it does not. Nothing is
installed here: for each missing tool the line says where its own instructions are.
"""

import asyncio
import importlib.util
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from forja.cli.console import Console
from forja.cli.detect import Detection, installed_clis
from forja.cli.prepare import LOW_DISK_GIB, Refused, prove
from forja.cli.session import repo_python
from forja.cli.settings import Perfil
from forja.core.adapters.executor import locate_in_path
from forja.executors import DEFAULT_CLI, KNOWN_CLIS
from forja.executors.probe import executable_version, version_problem

GITLEAKS_HELP = "https://github.com/gitleaks/gitleaks (as instruções de instalação estão no README)"
GIT_HELP = "https://git-scm.com/downloads"
GO_HELP = "https://go.dev/doc/install"
GOLANGCI_HELP = "https://golangci-lint.run/welcome/install/"
NODE_HELP = "https://nodejs.org/en/download"
DOTNET_HELP = "https://dotnet.microsoft.com/download"
JAVA_HELP = "https://adoptium.net/installation/"
MAVEN_HELP = "https://maven.apache.org/install.html"


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str
    fix: str = ""
    required: bool = True


def _module(name: str, purpose: str) -> Check:
    found = importlib.util.find_spec(name) is not None
    return Check(
        name,
        found,
        f"{purpose} (vem com a Forja)" if found else f"{purpose}: não encontrado",
        "" if found else "reinstale a Forja: `uv tool install forja` ou `pip install forja`",
    )


async def _pytest_in(repo: Path) -> Check:
    python = repo_python(repo)
    process = await asyncio.create_subprocess_exec(
        *python,
        "-c",
        "import pytest",
        cwd=repo,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    ok = await process.wait() == 0
    return Check(
        "pytest no repositório",
        ok,
        f"{python[0]} importa pytest" if ok else f"{python[0]} não importa pytest",
        "" if ok else "crie o ambiente do projeto e instale as dependências de teste nele",
    )


def _go_checks(environ: Mapping[str, str]) -> list[Check]:
    path = environ.get("PATH")
    found = locate_in_path("go", path) is not None
    lint = locate_in_path("golangci-lint", path) is not None
    return [
        Check(
            "go",
            found,
            "go no PATH" if found else "go ausente",
            "" if found else GO_HELP,
        ),
        Check(
            "golangci-lint",
            lint,
            "golangci-lint no PATH"
            if lint
            else "golangci-lint ausente: o lint de Go fica não suportado",
            "" if lint else f"instale seguindo {GOLANGCI_HELP}",
            required=False,
        ),
    ]


def _node_checks(environ: Mapping[str, str]) -> list[Check]:
    found = locate_in_path("node", environ.get("PATH")) is not None
    return [
        Check(
            "node",
            found,
            "node no PATH" if found else "node ausente",
            "" if found else NODE_HELP,
        )
    ]


def _dotnet_checks(environ: Mapping[str, str]) -> list[Check]:
    found = locate_in_path("dotnet", environ.get("PATH")) is not None
    return [
        Check(
            "dotnet",
            found,
            "dotnet no PATH" if found else "dotnet ausente",
            "" if found else DOTNET_HELP,
        )
    ]


def _java_checks(environ: Mapping[str, str]) -> list[Check]:
    java = locate_in_path("java", environ.get("PATH")) is not None
    maven = locate_in_path("mvn", environ.get("PATH")) is not None
    return [
        Check("java", java, "java no PATH" if java else "java ausente", "" if java else JAVA_HELP),
        Check(
            "maven",
            maven,
            "mvn no PATH" if maven else "mvn ausente",
            "" if maven else MAVEN_HELP,
        ),
    ]


async def run_checks(
    detection: Detection,
    profile: Perfil,
    environ: Mapping[str, str],
    console: Console,
    cache: Path,
    *,
    cli: str = "",
) -> list[Check]:
    name = cli or profile.cli or DEFAULT_CLI
    checks = [
        Check("git", detection.git, "git no PATH" if detection.git else "git ausente", GIT_HELP),
        _module("ruff", "lint do código do projeto"),
        _module("lizard", "complexidade ciclomática"),
        Check(
            "gitleaks",
            detection.gitleaks,
            "gitleaks no PATH" if detection.gitleaks else "gitleaks ausente",
            "" if detection.gitleaks else f"instale seguindo {GITLEAKS_HELP}",
        ),
        Check(
            "disco",
            detection.disk_free_gib >= LOW_DISK_GIB,
            f"{detection.disk_free_gib:.1f} GiB livres",
            f"libere ao menos {LOW_DISK_GIB:.0f} GiB",
        ),
    ]
    if detection.repo is not None:
        checks.append(
            Check(
                "repositório limpo",
                not detection.changed,
                "sem alterações não salvas"
                if not detection.changed
                else f"{len(detection.changed)} arquivo(s) alterado(s)",
                "faça commit ou stash antes de rodar a Forja",
            )
        )
        if detection.python:
            checks.append(await _pytest_in(detection.repo))
        if detection.go:
            checks += _go_checks(environ)
        if detection.typescript:
            checks += _node_checks(environ)
        if detection.csharp:
            checks += _dotnet_checks(environ)
        if detection.java:
            checks += _java_checks(environ)
    checks.append(await _agent_check(name, profile, environ, console, cache))
    checks += await _other_clis(name, profile, environ)
    return checks


async def _other_clis(chosen: str, profile: Perfil, environ: Mapping[str, str]) -> list[Check]:
    """The other known CLIs that are installed: a run can give one of them the tests. They are
    only listed here; the proof of life runs when a run uses one."""
    checks = []
    for name, make in KNOWN_CLIS.items():
        found = installed_clis(name, environ, profile.executaveis) if name != chosen else []
        if found:
            version = await executable_version(make(), found[0].path)
            checks.append(
                Check(
                    f"CLI {name}", True, f"{found[0].path} ({version or '?'}) instalada", "", False
                )
            )
    return checks


async def _agent_check(
    name: str, profile: Perfil, environ: Mapping[str, str], console: Console, cache: Path
) -> Check:
    label = f"CLI {name}"
    if name not in KNOWN_CLIS:
        return Check(label, False, "CLI desconhecida", f"conheço: {', '.join(KNOWN_CLIS)}")
    found = installed_clis(name, environ, profile.executaveis)
    if not found:
        return Check(
            label,
            False,
            "não encontrada no PATH",
            "instale a CLI e entre na sua conta antes; a Forja não faz isso por você",
        )
    adapter = KNOWN_CLIS[name]()
    version = await executable_version(adapter, found[0].path)
    if problem := version_problem(adapter, version):
        return Check(label, False, problem, "atualize a CLI")
    try:
        await prove(name, found[0], environ, cache, console)
    except Refused as refused:
        return Check(label, False, refused.message, "corrija a CLI e rode `forja doctor`")
    return Check(label, True, f"{found[0].path} ({version}) responde a uma tarefa de teste")


def terminal_note(platform: str, environ: Mapping[str, str]) -> str:
    return (
        "A Forja roda neste terminal e não cria sandbox: leitura fora da cópia e rede são "
        "garantidas pelo seu ambiente."
    )


def render(checks: list[Check], note: str = "") -> list[str]:
    lines = []
    for check in checks:
        mark = "ok " if check.ok else "FALTA"
        lines.append(f"[{mark}] {check.name}: {check.detail}")
        if not check.ok and check.fix:
            lines.append(f"        -> {check.fix}")
    if note:
        lines += ["", note]
    missing = [check for check in checks if not check.ok and check.required]
    lines += ["", "Tudo pronto." if not missing else f"{len(missing)} item(ns) a resolver."]
    return lines


async def doctor(
    detection: Detection,
    profile: Perfil,
    environ: Mapping[str, str],
    console: Console,
    cache: Path,
    *,
    cli: str = "",
) -> int:
    checks = await run_checks(detection, profile, environ, console, cache, cli=cli)
    for line in render(checks, terminal_note(sys.platform, environ)):
        console.say(line)
    return 0 if all(check.ok or not check.required for check in checks) else 1
