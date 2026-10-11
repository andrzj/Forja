"""``forja agente``: the only commands the agent may run, each one fixed and narrow.

The agent has no shell of its own. It may call ``forja agente testar|lint|medir`` to see what the
Forja's own gates will see, on its copy of the code, with the output cut short. The arguments are
only paths inside the working directory; anything else is refused, so the permission to run
``forja agente`` cannot be turned into running something else.
"""

import os
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

from forja.ui.glyphs import clean

PYTHON_VARIABLE = "FORJA_AGENT_PYTHON"
ISOLATED_VARIABLE = "FORJA_AGENT_ISOLATED"  # set only when the agent runs in a real sandbox
SAFE_ENVIRONMENT = ("PATH", "SYSTEMROOT", "TEMP", "TMP", "TMPDIR", "PATHEXT", "COMSPEC")
TIMEOUT_SECONDS = 600
TAIL_LINES = 80
COMMANDS = {
    "testar": "roda os testes do projeto (pytest), parando no primeiro erro",
    "lint": "roda o ruff no código",
    "medir": "mostra a complexidade ciclomática das funções (lizard)",
}


class Refused(Exception):
    """The call is not one the agent may make."""


def safe_paths(root: Path, given: Sequence[str]) -> list[str]:
    """Relative paths that exist under ``root``; nothing that looks like an option."""
    base = root.resolve()
    checked = []
    for item in given:
        if not item or item.startswith("-") or os.path.isabs(item) or ".." in Path(item).parts:
            raise Refused(f"caminho não permitido: {clean(item)!r}")
        target = (base / item).resolve()
        if not target.is_relative_to(base) or not target.exists():
            raise Refused(f"caminho não encontrado dentro do projeto: {clean(item)!r}")
        checked.append(item)
    return checked


def command_for(name: str, paths: list[str], environ: Mapping[str, str]) -> list[str]:
    own = [sys.executable, "-m"]
    match name:
        case "testar":
            if environ.get(ISOLATED_VARIABLE) != "1":
                raise Refused(
                    "testar roda código do projeto, que pode ter sido escrito por você; só é "
                    "permitido com isolamento real (incremento 1e). Use lint e medir."
                )
            python = environ.get(PYTHON_VARIABLE) or sys.executable
            return [python, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", *paths]
        case "lint":
            return [*own, "ruff", "check", "--no-cache", *(paths or ["."])]
        case "medir":
            return [*own, "lizard", *(paths or ["."])]
    raise Refused(f"comando desconhecido: {clean(name)!r}")


def tail(text: str, lines: int = TAIL_LINES) -> str:
    kept = text.splitlines()
    cut = len(kept) - lines
    shown = kept[-lines:] if cut > 0 else kept
    return "\n".join(([f"[... {cut} linhas anteriores omitidas]"] if cut > 0 else []) + shown)


def run_facade(argv: Sequence[str], cwd: Path, environ: Mapping[str, str]) -> int:
    if not argv or argv[0] not in COMMANDS:
        print("uso: forja agente testar|lint|medir [CAMINHO...]")
        return 2
    try:
        command = command_for(argv[0], safe_paths(cwd, argv[1:]), environ)
    except Refused as refused:
        print(refused)
        return 2
    try:
        done = subprocess.run(  # noqa: S603
            command,
            cwd=cwd,
            env={k: v for k, v in environ.items() if k.upper() in SAFE_ENVIRONMENT},
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        print(f"interrompido: passou de {TIMEOUT_SECONDS} s")
        return 124
    except OSError as error:
        print(f"não consegui rodar: {clean(str(error))}")
        return 127
    shown = tail(done.stdout + done.stderr).splitlines()
    print(chr(10).join(clean(line) for line in shown))
    return done.returncode
