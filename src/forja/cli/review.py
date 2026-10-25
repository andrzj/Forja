"""``forja revisao``: after the person fetched, what of a run reached the main branch.

It starts nothing and changes nothing in the repository. It reads the log of the run and the
history of the main branch, and writes the report to the data directory.
"""

import re
import tempfile
from collections import Counter
from collections.abc import Mapping
from pathlib import Path

from forja.cli.args import Arguments
from forja.cli.console import Console
from forja.cli.detect import Detection
from forja.cli.prepare import Refused
from forja.cli.resume import Unfinished, runs_of
from forja.cli.session import git_base_environment, git_executable
from forja.core.atomic import atomic_write_bytes
from forja.core.confirmation import ConfirmationError
from forja.core.events.errors import EventLogError
from forja.core.events.log import read_state
from forja.core.idempotency.git import Git, GitError
from forja.core.idempotency.reconcilers import run_branch_name
from forja.core.paths import forja_home
from forja.orchestrator.config import load_config
from forja.orchestrator.facts import Fact, FactsError, parse_facts
from forja.orchestrator.review import Landed, render_review
from forja.orchestrator.summary import read_facts

REVIEWS_DIR = "revisoes"
_COMMIT = re.compile(r"^[0-9a-f]{40}$")
# one line per commit: the Stage-Id and the Task-Id trailers, each joined by commas
_LOG_FORMAT = (
    "@@%(trailers:key=Stage-Id,valueonly,separator=%x2c)"
    "@@%(trailers:key=Task-Id,valueonly,separator=%x2c)"
)


def choose_run(runs: list[Unfinished], wanted: str) -> Unfinished:
    """The run asked for, or the newest of the repository."""
    if not runs:
        raise Refused("Nenhuma execução da Forja neste repositório. Rode `forja revisao` nele.")
    if not wanted:
        return runs[0]
    for run in runs:
        if run.run_id == wanted:
            return run
    raise Refused(f"A execução {wanted} não é deste repositório ou não existe.")


async def principal(git: Git, given: str) -> tuple[str, str]:
    """The main branch to read and the commit it is at: the one named, else ``origin/HEAD``."""
    name = given
    if not name:
        result = await git.run("symbolic-ref", "--short", "refs/remotes/origin/HEAD")
        if result.exit_code != 0 or not result.lines:
            raise Refused(
                "Não sei qual é a branch principal (não há `origin/HEAD`). Diga qual: "
                "`forja revisao --principal origin/main`."
            )
        name = result.lines[0].strip()
    if name.startswith("-"):
        raise Refused(f"`{name}` não é um nome de branch.")
    found = await git.run("rev-parse", "--verify", "--quiet", f"{name}^{{commit}}")
    if found.exit_code != 0 or not found.lines:
        raise Refused(
            f"A branch principal `{name}` não existe. Faça o `git fetch` e confira o nome."
        )
    return name, found.lines[0].strip()


async def read_landed(git: Git, base: str, main_commit: str) -> Landed:
    """The trailers on the commits that are on the main branch and were not in ``base``."""
    if not _COMMIT.fullmatch(base) or not await git.succeeds(
        "cat-file", "-e", f"{base}^{{commit}}"
    ):
        raise Refused(f"O commit de partida da execução ({base[:12]}) não está neste repositório.")
    stages: set[str] = set()
    loose: Counter[str] = Counter()
    for line in await git.lines("log", f"--format={_LOG_FORMAT}", f"{base}..{main_commit}"):
        parts = line.split("@@")
        if len(parts) != 3 or parts[0]:
            continue
        found = {value.strip() for value in parts[1].split(",") if value.strip()}
        stages |= found
        if not found:
            loose.update(value.strip() for value in parts[2].split(",") if value.strip())
    return Landed(frozenset(stages), dict(loose))


def read_comments(path: Path | None) -> tuple[Fact, ...]:
    if path is None:
        return ()
    try:
        return parse_facts(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as error:
        reason = error.strerror if isinstance(error, OSError) and error.strerror else "não é UTF-8"
        raise Refused(f"Não consegui ler os comentários ({path}): {reason}.") from None
    except FactsError as error:
        raise Refused(f"Os comentários em {path} não servem: {error}.") from None


async def revisao(
    args: Arguments, console: Console, environ: Mapping[str, str], detection: Detection
) -> int:
    if detection.repo is None:
        raise Refused("Rode `forja revisao` dentro do repositório da execução.")
    home = forja_home(environ=environ)
    run = choose_run(runs_of(home, detection.repo), args.run)
    facts = read_comments(args.facts)
    log = run.directory / "events.jsonl"
    try:
        state = read_state(log, run.run_id)
        config = load_config(state)
    except (EventLogError, ConfirmationError) as error:
        raise Refused(f"Não consegui ler o log da execução {run.run_id}: {error}.") from None
    with tempfile.TemporaryDirectory(prefix="forja-revisao-") as scratch:
        git = Git(
            detection.repo,
            executable=git_executable(),
            env=git_base_environment(environ),
            timeout=60,
            log_dir=Path(scratch),
        )
        try:
            main, main_commit = await principal(git, args.main_ref)
            landed = await read_landed(git, config.base_commit, main_commit)
        except GitError as error:
            raise Refused(f"O git falhou: {error}.") from None
    text = render_review(
        state,
        config,
        read_facts(log).premises,
        landed,
        facts,
        run_branch=run_branch_name(run.run_id),
        main=main,
        main_commit=main_commit,
        run_state=run.state,
    )
    report = home / REVIEWS_DIR / f"{run.run_id}.md"
    atomic_write_bytes(report, text.encode("utf-8"))
    console.say(f"Relatório da revisão da execução {run.run_id}: {report}")
    return 0
