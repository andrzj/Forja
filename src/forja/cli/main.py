"""``forja``: the door. It detects, asks what it must, proves the agent, confirms once and runs.

Exit codes are the ones of ``ExitCode``: 0 delivered, 1 failed, 2 could not start (something to
fix), 3 stopped with everything saved, 130 stopped by the person.
"""

import asyncio
import os
import sys
from collections.abc import Awaitable, Mapping
from pathlib import Path

from forja.cli.args import Arguments, parse
from forja.cli.console import Console, TerminalConsole, choose, confirm
from forja.cli.detect import Detection, detect
from forja.cli.doctor import doctor
from forja.cli.facade import run_facade
from forja.cli.keys import terminal_keys
from forja.cli.prepare import Prepared, Refused, confirmed, prepare, probe_cache
from forja.cli.resume import Unfinished, discard, find_unfinished, removal_commands
from forja.cli.run import Ended, ForcedExit, Renderer, closing_lines, execute, exit_code
from forja.cli.session import PolicyChanged, Session, open_session
from forja.cli.settings import (
    Execucao,
    Perfil,
    SettingsError,
    load_execucao,
    load_perfil,
    profile_dir,
    save_execucao,
    save_perfil,
)
from forja.core.locking.repository import RepositoryBusy
from forja.core.paths import forja_home
from forja.core.policy.config import PolicyConfigError
from forja.orchestrator.config import Objective
from forja.orchestrator.outcome import ExitCode
from forja.ui import terminal
from forja.ui.full import FullRenderer
from forja.ui.live import LiveRenderer
from forja.ui.plain import PlainRenderer
from forja.ui.terminal import Tier
from forja.ui.theme import theme_named, with_ascii


def renderer_for(profile: Perfil, saved: Execucao | None, console: Console) -> Renderer:
    """The screen for this terminal: the full screen when there is room, then the live line,
    then plain text for a pipe or CI."""
    caps = terminal.detect()
    style = saved.interface if saved else profile.interface
    forced = None if style.modo == "auto" else Tier(style.modo)
    tier, why = terminal.choose_tier(caps, forced, full_available=True)
    if why:
        console.say(why)
    if tier is Tier.TEXT:
        return PlainRenderer(sys.stdout)
    theme = theme_named(style.tema or None, dark_background=caps.dark_background)
    if style.ascii or not caps.unicode:
        theme = with_ascii(theme)
    if tier is Tier.FULL:
        return FullRenderer(theme, caps, resize=style.redimensionar)
    return LiveRenderer(theme, caps)


async def _pending(pending: list[Unfinished], console: Console, *, automatic: bool) -> str:
    """``resume``, ``discard`` or ``new`` for the run left unfinished in this repository."""
    latest = pending[0]
    console.say(
        f"Há uma execução incompleta neste repositório ({latest.run_id}, em {latest.state}"
        + (f": {latest.reason}" if latest.reason else "")
        + ")."
    )
    if automatic:
        raise Refused("Resolva a execução incompleta (rode `forja` sem --config) antes.")
    answer = choose(console, "O que fazer?", ["retomar de onde parou", "descartar e recomeçar"])
    return "resume" if answer == 0 else "discard"


def _remember(prepared: Prepared, profile: Perfil, console: Console, home: Path) -> None:
    if prepared.remember is None:
        return
    name, path = prepared.remember
    if confirm(console, f"Lembrar de usar sempre {path} para {name}?"):
        profile.cli = name
        profile.executaveis[name] = path
        save_perfil(home, profile)


def _finish(session: Session, ended: Ended, console: Console) -> int:
    for line in closing_lines(session, ended):
        console.say(line)
    return exit_code(session, ended)


async def _run(session: Session, renderer: Renderer, console: Console) -> int:
    keys = renderer.keys_source if isinstance(renderer, FullRenderer) else terminal_keys()
    try:
        ended = await execute(session, renderer, keys)
    except ForcedExit:
        if isinstance(renderer, FullRenderer):
            renderer.abort()
            await _screen(renderer.closed(), console)
        console.say(
            "Saiu sem esperar. O que já estava gravado está salvo; rode `forja` para retomar."
        )
        return int(ExitCode.INTERRUPTED)
    finally:
        if keys is not None:
            keys.close()
        session.close()
    lines = closing_lines(session, ended)
    if isinstance(renderer, FullRenderer):
        await _screen(renderer.finish(lines), console)
    return _finish(session, ended, console)


async def _screen(waiting: Awaitable[None], console: Console) -> None:
    """Wait for the full screen to close; if it broke, the run is unaffected and this says so."""
    try:
        await waiting
    except Exception as error:  # noqa: BLE001 - a broken screen must never lose the result
        console.say(f"A tela completa falhou ({error}); o resultado da execução continua valendo.")


async def _discard(latest: Unfinished, console: Console) -> None:
    discard(latest.directory)
    console.say(f"Execução {latest.run_id} descartada. Nada foi apagado. Para limpar as branches:")
    for command in removal_commands(latest.run_id):
        console.say(f"  {command}")


async def start(
    args: Arguments, console: Console, environ: Mapping[str, str], detection: Detection
) -> int:
    home = profile_dir(environ)
    profile = load_perfil(home)
    saved = load_execucao(args.config) if args.config else None
    automatic = args.config is not None or not console.interactive
    if detection.repo is not None and not args.plan_only:
        pending = find_unfinished(forja_home(environ=environ), detection.repo)
        if pending:
            if await _pending(pending, console, automatic=automatic) == "resume":
                session = await open_session(
                    None, run_id=pending[0].run_id, environ=environ, interactive=not automatic
                )
                return await _run(session, renderer_for(profile, saved, console), console)
            await _discard(pending[0], console)
    prepared = await prepare(args, detection, profile, home, console, environ, saved=saved)
    if args.plan_only:
        for line in prepared.summary:
            console.say(line)
        return 0
    if prepared.config.objective is Objective.FIX:  # until the two-stage task exists (3a, step 4)
        raise Refused("`forja corrigir` já prepara o conserto, mas ainda não o executa.")
    if not confirmed(console, prepared, automatic=automatic):
        console.say("Cancelado. Nada foi alterado.")
        return 0
    _remember(prepared, profile, console, home)
    session = await open_session(prepared.config, environ=environ, interactive=not automatic)
    save_execucao(session.directory / "execucao.toml", prepared.execucao)
    return await _run(session, renderer_for(profile, saved, console), console)


async def amain(args: Arguments, console: Console, environ: Mapping[str, str]) -> int:
    try:
        detection = await detect(Path.cwd(), environ)
        if args.command == "doctor":
            profile = load_perfil(profile_dir(environ))
            cache = probe_cache(profile_dir(environ))
            return await doctor(detection, profile, environ, console, cache, cli=args.cli)
        if args.command == "agente":
            return run_facade(args.agent, Path.cwd(), environ)
        return await start(args, console, environ, detection)
    except Refused as refused:
        console.say(refused.message)
        return refused.code
    except (PolicyChanged, PolicyConfigError) as error:
        console.say(str(error))
        return int(ExitCode.INVALID_CONFIG)
    except SettingsError as error:
        console.say(str(error))
        return int(ExitCode.INVALID_CONFIG)
    except RepositoryBusy:
        console.say("Já há uma execução da Forja em andamento neste repositório.")
        return int(ExitCode.INVALID_CONFIG)


def main(argv: list[str] | None = None) -> int:
    args = parse(argv)
    try:
        return asyncio.run(amain(args, TerminalConsole(), dict(os.environ)))
    except KeyboardInterrupt:
        return int(ExitCode.INTERRUPTED)


if __name__ == "__main__":
    sys.exit(main())
