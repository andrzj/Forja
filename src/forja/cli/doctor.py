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
from forja.cli.detect import KNOWN_CLIS, Detection, installed_clis
from forja.cli.prepare import LOW_DISK_GIB, Refused, prove
from forja.cli.session import repo_python
from forja.cli.settings import Perfil
from forja.executors.probe import executable_version, version_problem

GITLEAKS_HELP = "https://github.com/gitleaks/gitleaks (as instruções de instalação estão no README)"
GIT_HELP = "https://git-scm.com/downloads"


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


async def run_checks(
    detection: Detection,
    profile: Perfil,
    environ: Mapping[str, str],
    console: Console,
    cache: Path,
    *,
    cli: str = "",
) -> list[Check]:
    name = cli or profile.cli or "claude-code"
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
    checks.append(await _agent_check(name, profile, environ, console, cache))
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
