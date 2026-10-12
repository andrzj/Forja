"""The guided preparation: detect, ask only what cannot be detected, prove the CLI, confirm once.

After the confirmation there are no more questions. Everything that is asked here is also what
``execucao.toml`` holds, so ``forja --config`` can run the same thing without a person.
"""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from forja.cli.args import VERBS, Arguments
from forja.cli.console import Console, choose, confirm
from forja.cli.detect import KNOWN_CLIS, Detection, installed_clis
from forja.cli.session import new_config, repo_policy
from forja.cli.settings import Execucao, Perfil
from forja.core.adapters.executor import ExecutorChoice
from forja.core.policy.config import PolicyConfigError
from forja.executors.probe import executable_version, run_probe, version_problem
from forja.orchestrator.config import RunConfig

AVAILABLE = frozenset({"refatorar"})
LOW_DISK_GIB = 2.0


class Refused(Exception):
    """The preparation cannot go on; ``message`` says why and what to do."""

    def __init__(self, message: str, code: int = 2) -> None:
        super().__init__(message)
        self.message = message
        self.code = code


@dataclass(frozen=True)
class Prepared:
    config: RunConfig
    execucao: Execucao
    summary: tuple[str, ...]
    remember: tuple[str, str] | None  # (cli name, path) the person chose and may want kept


def objective_of(args: Arguments, saved: Execucao | None, console: Console) -> str:
    """The verb asked for, or the answer to the menu; only what exists can be run."""
    verb = args.command if args.command in VERBS else (saved.objetivo if saved else "")
    if not verb:
        names = list(VERBS)
        options = [
            f"{name}: {VERBS[name]}" + ("" if name in AVAILABLE else "  [ainda não disponível]")
            for name in names
        ]
        verb = names[choose(console, "O que você quer fazer?", options, default=1)]
    if verb not in AVAILABLE:
        raise Refused(f"`forja {verb}` ainda não está disponível: {VERBS[verb]}.")
    return verb


def check_repository(detection: Detection) -> Path:
    if not detection.git:
        raise Refused("O git não está instalado ou não está no PATH. Rode `forja doctor`.")
    if detection.greenfield:
        raise Refused(
            "Este diretório está vazio ou sem commits. Criar a partir de uma ideia fica "
            "disponível no incremento 6; por enquanto a Forja trabalha em repositórios "
            "existentes."
        )
    if detection.repo is None:
        raise Refused("Rode `forja` dentro de um repositório git.")
    if not detection.python:
        raise Refused(
            "Não encontrei pyproject.toml neste repositório. Por enquanto a Forja trabalha "
            "com Python (outras linguagens chegam nos incrementos 3 e 5)."
        )
    if detection.changed:
        sample = ", ".join(detection.changed[:3])
        raise Refused(
            f"Há {len(detection.changed)} arquivo(s) com alterações não salvas ({sample}). "
            "Faça commit ou stash antes: a Forja nunca mexe no que você ainda não salvou."
        )
    return detection.repo


def choose_cli(
    args: Arguments,
    saved: Execucao | None,
    profile: Perfil,
    environ: Mapping[str, str],
    console: Console,
) -> tuple[str, ExecutorChoice, bool]:
    """The CLI by name and where it is; whether the choice is worth offering to keep."""
    name = args.cli or (saved.cli if saved else "") or profile.cli or "claude-code"
    if name not in KNOWN_CLIS:
        raise Refused(f"Não conheço a CLI `{name}`. As que conheço: {', '.join(KNOWN_CLIS)}.")
    explicit = Path(saved.executavel) if saved and saved.executavel else None
    found = installed_clis(name, environ, profile.executaveis, explicit)
    if not found:
        raise Refused(
            f"Não encontrei `{name}` instalado. Instale e entre na sua conta antes de usar a "
            "Forja (rode `forja doctor` para ver o que falta)."
        )
    if len(found) == 1:
        return name, found[0], False
    options = [f"{item.path} ({item.source.value})" for item in found]
    return (
        name,
        found[choose(console, f"Encontrei {len(found)} instalações de {name}:", options)],
        True,
    )


def probe_cache(directory: Path) -> Path:
    return directory / "provas.json"


async def prove(
    name: str, choice: ExecutorChoice, environ: Mapping[str, str], cache: Path, console: Console
) -> str:
    """The version of the CLI, after proving it works; remembered per path and version."""
    adapter = KNOWN_CLIS[name]()
    version = await executable_version(adapter, choice.path)
    if problem := version_problem(adapter, version):
        raise Refused(f"{choice.path}: {problem}.")
    assert version is not None
    key = f"{choice.path}|{version}"
    try:
        proven = json.loads(cache.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        proven = {}
    if key in proven:
        return version
    console.say(f"Provando que {name} {version} funciona (uma tarefa de teste)…")
    problems = await run_probe(adapter, choice.path, environ)
    if problems:
        raise Refused(
            f"A prova de vida de {name} falhou: {problems[0]}\n"
            "A configuração da CLI (login, modelo, gateway) é sua e precisa estar pronta antes. "
            "Corrija e rode `forja doctor`."
        )
    proven[key] = True
    try:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(proven), encoding="utf-8")
    except OSError:
        pass  # the proof is only a shortcut for next time
    return version


def summary_of(
    detection: Detection, config: RunConfig, scope: tuple[str, ...], tokens: int
) -> tuple[str, ...]:
    where = ", ".join(scope) if scope else "todo o código"
    tests = (
        "o agente pode rodar os testes do projeto na cópia dele (`agente_roda_testes = false` "
        "no execucao.toml desliga)"
        if config.agent_runs_tests
        else "o agente não roda os testes; só edita e consulta lint e complexidade"
    )
    return (
        f"Vou refatorar {detection.repo.name if detection.repo else ''} "
        f"(branch {detection.branch}, commit {detection.head[:7]}).",
        f"  agente: {config.implementer.name} {config.implementer.version}",
        f"  onde: {where}",
        f"  limite: {format(tokens, ',').replace(',', '.')} tokens, até {config.budget.tasks} tarefas",
        "  ambiente: este terminal. A Forja não cria sandbox: leitura fora da cópia e rede "
        "são garantidas pelo seu ambiente",
        "  a Forja impõe: ambiente filtrado para a CLI, cópia sem .git e sem arquivos sensíveis, "
        "ferramentas de arquivo do agente confinadas à cópia, git conferido a cada chamada",
        f"  testes: {tests}",
        "  entrega: uma branch nova `forja-run/…`; sua branch não é alterada e nada é enviado",
    )


async def prepare(
    args: Arguments,
    detection: Detection,
    profile: Perfil,
    profile_dir: Path,
    console: Console,
    environ: Mapping[str, str],
    *,
    saved: Execucao | None = None,
) -> Prepared:
    objective_of(args, saved, console)
    repo = check_repository(detection)
    try:
        repo_policy(repo)
    except PolicyConfigError as error:
        raise Refused(f"O forja.toml deste repositório tem erros:\n{error}") from None
    if detection.disk_free_gib < LOW_DISK_GIB:
        raise Refused(f"Só há {detection.disk_free_gib:.1f} GiB livres; a Forja pede ao menos 2.")
    name, choice, offer = choose_cli(args, saved, profile, environ, console)
    version = await prove(name, choice, environ, probe_cache(profile_dir), console)
    scope = args.scope or tuple(saved.escopo if saved else ())
    tokens = saved.tokens if saved else 2_000_000
    runs_tests = saved.agente_roda_testes if saved else True
    tasks = saved.tarefas if saved else 5
    config = new_config(
        repo=repo, base_commit=detection.head, executor_name=name, executor_path=choice.path,
        executor_version=version, tokens=tokens, scope=scope,
        agent_runs_tests=runs_tests, tasks=tasks,
    )  # fmt: skip
    lines = summary_of(detection, config, scope, tokens)
    execucao = Execucao(
        cli=name,
        executavel=str(choice.path),
        escopo=list(scope),
        tokens=tokens,
        agente_roda_testes=runs_tests,
        tarefas=tasks,
        interface=saved.interface if saved else profile.interface,
    )
    return Prepared(config, execucao, lines, (name, str(choice.path)) if offer else None)


def confirmed(console: Console, prepared: Prepared, *, automatic: bool) -> bool:
    for line in prepared.summary:
        console.say(line)
    if automatic:
        return True
    return confirm(console, "Confirma e começa? Depois disso a Forja não faz mais perguntas.")
