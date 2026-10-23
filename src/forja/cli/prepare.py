"""The guided preparation: detect, ask only what cannot be detected, prove the CLI, confirm once.

After the confirmation there are no more questions. Everything that is asked here is also what
``execucao.toml`` holds, so ``forja --config`` can run the same thing without a person.
"""

import json
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from forja.cli.args import VERBS, Arguments
from forja.cli.console import Console, choose, confirm
from forja.cli.detect import Detection, installed_clis
from forja.cli.security_notes import NO_LICENSES, UNMEASURED, e2e_notices
from forja.cli.semgrep_rules import RulesError, explicit_rules, rules_in_commit
from forja.cli.session import (
    e2e_commands,
    executor_ref,
    git_base_environment,
    git_executable,
    new_config,
    policy_digest,
    repo_policy,
    standard_settings,
)
from forja.cli.settings import Execucao, Perfil
from forja.core.adapters.executor import ExecutorChoice
from forja.core.artifacts.schemas import CriteriaBody
from forja.core.idempotency.git import Git
from forja.core.policy.config import EffectivePolicy, PolicyConfigError
from forja.core.redaction import RedactionSettings
from forja.executors import DEFAULT_CLI, KNOWN_CLIS
from forja.executors.probe import executable_version, run_probe, version_problem
from forja.orchestrator.config import ExecutorRef, FixRequest, Objective, RunConfig

AVAILABLE = frozenset({"refatorar", "corrigir"})
CRITERIA_FILE = "criterios.json"
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


def _read_text(path: Path, what: str) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        reason = error.strerror if isinstance(error, OSError) and error.strerror else "não é UTF-8"
        raise Refused(f"Não consegui ler {what} ({path}): {reason}.") from None


def read_fix(args: Arguments, saved: Execucao | None) -> tuple[FixRequest, str, str]:
    """The defect and the criteria of ``forja corrigir``, with where each one came from.

    The description is the text on the command line, else the ``-f`` file. The criteria are the
    ``--criterios`` file, else ``criterios.json`` beside the ``-f`` file. Both come back also
    as the strings ``execucao.toml`` keeps, so ``--config`` reproduces the run.
    """
    file = args.file or (Path(saved.arquivo) if saved and saved.arquivo else None)
    description = args.text.strip() or (saved.descricao.strip() if saved else "")
    if not description and file is not None:
        description = _read_text(file, "a descrição do erro").strip()
    if not description:
        raise Refused('Descreva o erro: `forja corrigir "texto"` ou `forja corrigir -f arquivo`.')
    path = args.criteria or (Path(saved.criterios) if saved and saved.criterios else None)
    if path is None and file is not None and (file.parent / CRITERIA_FILE).is_file():
        path = file.parent / CRITERIA_FILE
    if path is None:
        raise Refused(
            "Faltam os critérios do conserto: passe `--criterios arquivo.json` "
            f"(ou deixe um `{CRITERIA_FILE}` ao lado do arquivo dado em -f). "
            'Formato: {"criteria": [{"id": 1, "text": "...", "level": "unit", "origin": "..."}]}.'
        )
    try:
        criteria = CriteriaBody.model_validate_json(_read_text(path, "os critérios"))
    except ValidationError as error:
        first = error.errors()[0]
        where = ".".join(str(part) for part in first["loc"]) or "arquivo"
        raise Refused(f"Os critérios em {path} não servem: {where}: {first['msg']}.") from None
    return FixRequest(description=description, criteria=criteria), description, str(path.resolve())


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
    if not (
        detection.python
        or detection.go
        or detection.typescript
        or detection.csharp
        or detection.java
    ):
        raise Refused(
            "Não encontrei nenhuma linguagem neste repositório (pyproject.toml, go.mod, "
            "package.json com tsconfig.json, .sln ou .csproj, pom.xml ou build.gradle[.kts])."
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
    *,
    tests: bool = False,
) -> tuple[str, ExecutorChoice, bool]:
    """The CLI by name and where it is; whether the choice is worth offering to keep.

    ``tests`` asks for the CLI of the test author, which has no default of its own: the caller
    only asks when ``--cli-testes`` or the saved ``cli_testes`` names one.
    """
    if tests:
        name = args.cli_tests or (saved.cli_testes if saved else "")
        path = saved.executavel_testes if saved else ""
    else:
        name = args.cli or (saved.cli if saved else "") or profile.cli or DEFAULT_CLI
        path = saved.executavel if saved else ""
    if name not in KNOWN_CLIS:
        raise Refused(f"Não conheço a CLI `{name}`. As que conheço: {', '.join(KNOWN_CLIS)}.")
    explicit = Path(path) if path else None
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


def policy_changes(policy: EffectivePolicy) -> tuple[str, ...]:
    """What the repository's ``forja.toml`` changes from the Forja's own defaults, in words.

    A repository can loosen a gate, run its own command in place of the Forja's or switch off a
    detector, so the person who confirms has to see it all, with the values: it is the
    repository's decision, not the Forja's.
    """
    defaults = standard_settings()
    notes = []
    for check_id, check in sorted(policy.checks.items()):
        if check.settings != defaults.get(check_id):
            on = check.settings.on_inconclusive
            how = check.settings.mode.value + (f", se não puder medir: {on.value}" if on else "")
            notes.append(f"{check_id}: modo ou política diferente do padrão ({how})")
        for name, argv in sorted(check.commands.items()):
            notes.append(f"{check_id}: roda no lugar do padrão ({name}): {' '.join(argv)}")
        for language, limits in sorted(check.thresholds.items()):
            for name, value in sorted(limits.items()):
                notes.append(f"{check_id}: limite {name} de {language} = {value}")
        for name, value in sorted(check.limits.items()):
            notes.append(f"{check_id}: limite {name} = {value}")
        if check.promotion is not None:
            notes.append(f"{check_id}: promovido de observação a bloqueio ({check.promotion.date})")
    for language, commands in sorted(policy.adapter_commands.items()):
        for name, argv in sorted(commands.items()):
            notes.append(f"{language}: roda no lugar do padrão ({name}): {' '.join(argv)}")
    notes += _redaction_changes(policy)
    return tuple(notes)


def _redaction_changes(policy: EffectivePolicy) -> list[str]:
    redaction, standard = policy.redaction, RedactionSettings()
    notes = []
    if redaction.allow or redaction.allow_patterns:
        notes.append("redação: valores liberados pelo repositório (nunca mascarados)")
    off = sorted(kind.value for kind in standard.pii - redaction.pii)
    if off:
        notes.append(f"redação: detectores de dados pessoais desligados: {', '.join(off)}")
    if redaction.entropy_threshold > standard.entropy_threshold:
        notes.append(f"redação: limiar de entropia mais alto ({redaction.entropy_threshold})")
    return notes


NO_RULES = (
    "SAST NÃO EXECUTADO: sem configuração. A Forja não traz regras do Semgrep; forneça as suas "
    "com --semgrep-config ou deixe .semgrep.yml ou .semgrep/ no repositório"
)


async def semgrep_rules(
    args: Arguments, saved: Execucao | None, repo: Path, commit: str, environ: Mapping[str, str]
) -> tuple[str, str]:
    """The rules the person named (as an absolute path, else empty) and the summary line about
    the SAST. Rules a repository carries are read from the base commit."""
    named = args.semgrep_config or (saved.semgrep_config if saved else "")
    try:
        if named:
            path = explicit_rules(named)
            return str(path), f"SAST: Semgrep com as regras em {path}"
        with tempfile.TemporaryDirectory(prefix="forja-rules-") as scratch:
            git = Git(
                repo,
                executable=git_executable(),
                env=git_base_environment(environ),
                timeout=30,
                log_dir=Path(scratch),
            )
            found = await rules_in_commit(git, commit)
    except RulesError as error:
        raise Refused(str(error)) from None
    if found:
        return "", f"SAST: Semgrep com as regras do repositório ({', '.join(found)})"
    return "", NO_RULES


def summary_of(
    detection: Detection,
    config: RunConfig,
    scope: tuple[str, ...],
    tokens: int,
    policy_notes: tuple[str, ...] = (),
    sast: str = "",
    security: tuple[str, ...] = (),
) -> tuple[str, ...]:
    where = ", ".join(scope) if scope else "todo o código"
    limit = format(tokens, ",").replace(",", ".")
    tests = (
        "o agente pode rodar os testes do projeto na cópia dele (`agente_roda_testes = false` "
        "no execucao.toml desliga)"
        if config.agent_runs_tests
        else "o agente não roda os testes; só edita e consulta lint e complexidade"
    )
    fix = config.fix
    verb = "corrigir" if config.objective is Objective.FIX else "refatorar"
    return (
        f"Vou {verb} {detection.repo.name if detection.repo else ''} "
        f"(branch {detection.branch}, commit {detection.head[:7]}).",
        *(
            (f"  erro: {fix.description}", f"  critérios: {len(fix.criteria.criteria)}")
            if fix
            else ()
        ),
        *(
            (
                f"  agente que escreve os testes: {_agent(config.test_author)}",
                f"  agente que implementa: {_agent(config.implementer)}",
            )
            if config.test_author
            else (f"  agente: {_agent(config.implementer)}",)
        ),
        f"  onde: {where}",
        f"  limite: {limit} tokens, até {config.budget.tasks} tarefas",
        "  ambiente: este terminal. A Forja não cria sandbox: leitura fora da cópia e rede "
        "são garantidas pelo seu ambiente",
        "  a Forja impõe: ambiente filtrado para a CLI, cópia sem .git e sem arquivos sensíveis, "
        "ferramentas de arquivo do agente confinadas à cópia, git conferido a cada chamada",
        f"  testes: {tests}",
        *((f"  {sast}",) if sast else ()),
        *(f"  {line}" for line in security),
        "  entrega: uma branch nova `forja-run/…`; sua branch não é alterada e nada é enviado",
        *(("  forja.toml do repositório muda o padrão:", *(f"    {note}" for note in policy_notes))
          if policy_notes else ()),
    )  # fmt: skip


def _agent(executor: ExecutorRef) -> str:
    model = f", modelo {executor.model}" if executor.model else ""
    return f"{executor.name} {executor.version}{model}"


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
    verb = objective_of(args, saved, console)
    fixing = read_fix(args, saved) if verb == "corrigir" else None
    repo = check_repository(detection)
    try:
        policy = repo_policy(repo)
        notes = policy_changes(policy)
    except PolicyConfigError as error:
        raise Refused(f"O forja.toml deste repositório tem erros:\n{error}") from None
    if detection.disk_free_gib < LOW_DISK_GIB:
        raise Refused(f"Só há {detection.disk_free_gib:.1f} GiB livres; a Forja pede ao menos 2.")
    name, choice, offer = choose_cli(args, saved, profile, environ, console)
    version = await prove(name, choice, environ, probe_cache(profile_dir), console)
    model = args.model or (saved.modelo if saved else "")
    model_tests = args.model_tests or (saved.modelo_testes if saved else "")
    author: tuple[str, ExecutorChoice, str] | None = None
    tests_name = args.cli_tests or (saved.cli_testes if saved else "")
    if fixing and tests_name and tests_name != name:
        author_name, author_choice, _ = choose_cli(
            args, saved, profile, environ, console, tests=True
        )
        author_version = await prove(
            author_name, author_choice, environ, probe_cache(profile_dir), console
        )
        author = (author_name, author_choice, author_version)
    elif fixing and model_tests:  # the same CLI, another model
        author = (name, choice, version)
    scope = args.scope or tuple(saved.escopo if saved else ())
    rules, sast = await semgrep_rules(args, saved, repo, detection.head, environ)
    tokens = saved.tokens if saved else 2_000_000
    runs_tests = saved.agente_roda_testes if saved else True
    tasks = saved.tarefas if saved else 5
    config = new_config(
        repo=repo, base_commit=detection.head, executor_name=name, executor_path=choice.path,
        executor_version=version, executor_model=model, tokens=tokens, scope=scope,
        agent_runs_tests=runs_tests, tasks=tasks, semgrep_config=rules,
        policy_version=policy_digest(policy),
        fix=fixing[0] if fixing else None,
        test_author=executor_ref(author[0], author[1].path, author[2], model_tests)
        if author else None,
    )  # fmt: skip
    security = (
        *(() if policy.forbidden_licenses else (NO_LICENSES,)),
        UNMEASURED,
        *e2e_notices(declared=bool(e2e_commands(policy))),
    )
    lines = summary_of(detection, config, scope, tokens, notes, sast, security)
    execucao = Execucao(
        objetivo="corrigir" if fixing else "refatorar",
        descricao=fixing[1] if fixing else "",
        criterios=fixing[2] if fixing else "",
        cli=name,
        executavel=str(choice.path),
        cli_testes=author[0] if author else "",
        executavel_testes=str(author[1].path) if author else "",
        modelo=model,
        modelo_testes=model_tests,
        escopo=list(scope),
        tokens=tokens,
        agente_roda_testes=runs_tests,
        tarefas=tasks,
        semgrep_config=rules,
        interface=saved.interface if saved else profile.interface,
    )
    return Prepared(config, execucao, lines, (name, str(choice.path)) if offer else None)


def confirmed(console: Console, prepared: Prepared, *, automatic: bool) -> bool:
    for line in prepared.summary:
        console.say(line)
    if automatic:
        return True
    return confirm(console, "Confirma e começa? Depois disso a Forja não faz mais perguntas.")
