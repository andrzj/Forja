"""The summary of an execution: what the reviewer reads before the branch.

Written in Portuguese, to a file in the run directory and never into the repository. The numbers
come from the log, so a resumed run produces the same text as one that was never interrupted.
"""

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from forja.checks.readme import README_NAMES
from forja.core.artifacts.schemas import ExecutionSummaryBody, TaskOutcome, TaskOutcomeKind
from forja.core.confirmation import ConfirmationError, load_confirmation
from forja.core.events.state import RunState
from forja.core.events.versioning import BadLine, parse_line
from forja.core.isolation import Context, Guarantee, Status
from forja.core.states import AttemptState, Level, StageState, TaskState
from forja.orchestrator.config import RunConfig

METRICS = "metrics"
PREMISE = "premise"
DOCUMENTATION = "documentation"
TRACE = "trace"
ADR_DIR = "docs/adr/"
NOT_APPLICABLE = "Não se aplica nesta versão."


@dataclass(frozen=True)
class Premise:
    """Something the run went on without knowing: a check that could not measure (``check``), or
    what an agent declared it had to guess (``statement``, with why and what evidence was missing).

    ``stage`` is where it arose; the commits of that stage and of the later ones depend on it.
    """

    task: str
    attempt: str
    check: str
    stage: str = ""
    statement: str = ""
    reason: str = ""
    missing_evidence: str = ""

    @property
    def id(self) -> str:
        """A name the person can use in the facts file; the same premise has the same name."""
        what = self.check or self.statement
        return "p" + hashlib.sha256(f"{self.task}\n{what}".encode()).hexdigest()[:8]


@dataclass(frozen=True)
class Documented:
    """What a task's documenter left in the repository: its record and the other documents."""

    record: str
    files: tuple[str, ...]


@dataclass(frozen=True)
class Traced:
    """A criterion of a task: where in the input it comes from and the tests that cover it."""

    id: int
    text: str
    origin: tuple[str, ...]
    tests: tuple[str, ...]


@dataclass
class Facts:
    """What the log says that the states alone do not: assumptions and the measured numbers."""

    premises: list[Premise] = field(default_factory=list)
    documented: dict[str, Documented] = field(default_factory=dict)
    traced: dict[str, tuple[Traced, ...]] = field(default_factory=dict)
    baseline: dict[str, float] = field(default_factory=dict)
    final: dict[str, float] = field(default_factory=dict)


def read_facts(log_path: Path) -> Facts:
    facts = Facts()
    seen: set[Premise] = set()
    for raw in [line for line in log_path.read_bytes().split(b"\n") if line]:
        try:
            event = parse_line(raw)
        except BadLine:
            break
        if event.type != "progress":
            continue
        kind, payload = event.payload.get("kind"), event.payload
        if kind == PREMISE:
            premise = Premise(
                str(payload.get("task")),
                str(payload.get("attempt")),
                str(payload.get("check", "")),
                str(payload.get("stage", "")),
                str(payload.get("statement", "")),
                str(payload.get("reason", "")),
                str(payload.get("missing_evidence", "")),
            )
            if premise.id not in {known.id for known in seen}:
                seen.add(premise)
                facts.premises.append(premise)
        elif kind == DOCUMENTATION:
            files = payload.get("files")
            if isinstance(files, list):
                facts.documented[str(payload.get("task"))] = Documented(
                    str(payload.get("record")), tuple(str(f) for f in files)
                )
        elif kind == TRACE:
            rows = payload.get("criteria")
            if isinstance(rows, list):
                facts.traced[str(payload.get("task"))] = tuple(
                    _traced(row) for row in rows if isinstance(row, dict)
                )
        elif kind == METRICS:
            values = payload.get("values")
            if isinstance(values, dict):
                numbers = {
                    str(k): float(v)
                    for k, v in values.items()
                    if isinstance(v, int | float) and not isinstance(v, bool)
                }
                target = {"baseline": facts.baseline, "final": facts.final}.get(
                    str(payload.get("phase"))
                )
                if target is not None:
                    target.update(numbers)
    return facts


def _traced(row: Mapping[str, object]) -> Traced:
    origin, tests = row.get("origin"), row.get("tests")
    return Traced(
        int(str(row.get("id"))),
        str(row.get("text")),
        tuple(str(o) for o in origin) if isinstance(origin, list) else (),
        tuple(str(t) for t in tests) if isinstance(tests, list) else (),
    )


def task_outcomes(state: RunState) -> list[TaskOutcome]:
    outcomes = []
    for task in state.children_of(Level.TASK, state.run_id):
        current = state.state_of(Level.TASK, task)
        kind = TaskOutcomeKind.CANCELLED
        if current is TaskState.INTEGRATED:
            kind = TaskOutcomeKind.INTEGRATED
        elif current is TaskState.BLOCKED:
            kind = TaskOutcomeKind.BLOCKED
        states = _attempt_states(state, task)
        counted = [s for s in states if s is not AttemptState.DISCARDED]
        outcomes.append(
            TaskOutcome(
                task_id=task,
                outcome=kind,
                attempts=len(counted),
                rejected_attempts=counted.count(AttemptState.REJECTED),
            )
        )
    return outcomes


def _attempt_states(state: RunState, task: str) -> list[AttemptState]:
    states = []
    for stage in state.children_of(Level.STAGE, task):
        for attempt in state.children_of(Level.ATTEMPT, stage):
            current = state.state_of(Level.ATTEMPT, attempt)
            assert isinstance(current, AttemptState)
            states.append(current)
    return states


def summary_body(state: RunState) -> ExecutionSummaryBody:
    return ExecutionSummaryBody(tasks=tuple(task_outcomes(state)))


def render_summary(
    state: RunState,
    facts: Facts,
    config: RunConfig,
    run_branch: str,
    summary_path: Path,
    notices: tuple[str, ...] = (),
) -> str:
    lines = [
        f"# Resumo da execução {state.run_id}",
        "",
        f"Branch da entrega: `{run_branch}`, criada a partir de `{config.base_commit[:12]}`.",
        "",
        "## Premissas assumidas",
        "",
        *_premises(state, facts, config),
        "",
        "## Tarefas bloqueadas",
        "",
        *_blocked(state),
        "",
        "## Mudanças de comportamento",
        "",
        NOT_APPLICABLE,
        "",
        "## Refatorações",
        "",
        *_refactorings(state),
        "",
        "## Rastreabilidade",
        "",
        *_traceability(state, facts),
        "",
        "## Documentação",
        "",
        *_documentation(state, facts),
        "",
        "## Métricas antes e depois",
        "",
        *_metrics(facts),
        "",
        "## Ambiente e garantias",
        "",
        *_environment(state, config),
        *_agents(config),
        *(f"- **{notice}**" for notice in notices),
        "",
        "## Para publicar",
        "",
        f"A Forja não faz push. Se aprovar o resultado: `git push -u <remoto> {run_branch}`.",
        f"Este resumo fica em `{summary_path}` e não vai para o histórico.",
        "",
    ]
    return "\n".join(lines)


GUARANTEE_TEXT = {
    Guarantee.FILTERED_ENVIRONMENT: "ambiente filtrado para a CLI do agente",
    Guarantee.SENSITIVE_FILES_ABSENT: "arquivos sensíveis ausentes da cópia do agente",
    Guarantee.NO_DOT_GIT_IN_COPY: "cópia do agente sem `.git`",
    Guarantee.PROCESS_TREE_CONTAINED: "processos presos à Forja (não sobrevivem a ela)",
    Guarantee.NO_GIT_AVAILABLE: "uso de git em outro caminho",
    Guarantee.READ_RESTRICTED_TO_WORKCOPY: "leitura fora da cópia por código executado",
    Guarantee.NETWORK_ALLOWLIST: "acesso à rede",
    Guarantee.NO_SECRETS: "segredos do ambiente do usuário",
}
STATUS_TEXT = {
    Status.ENFORCED: "a Forja impôs",
    Status.DETECTED_ONLY: "a Forja só detecta (git conferido antes e depois de cada chamada)",
    Status.ENVIRONMENT: "ficou por conta do ambiente em que a Forja rodou",
}


def _environment(state: RunState, config: RunConfig) -> list[str]:
    """What the Forja imposed, what it only noticed and what it left to the environment."""
    try:
        record = load_confirmation(state).isolation
    except ConfirmationError:
        return ["Não registrado."]
    declared = record.declaration()[Context.AGENT]
    lines = [
        "A Forja rodou no terminal do usuário e não cria sandbox: a infraestrutura e as "
        "permissões em volta são do usuário ou da empresa.",
        "",
    ]
    for status in (Status.ENFORCED, Status.DETECTED_ONLY, Status.ENVIRONMENT):
        for guarantee in Guarantee:
            if declared[guarantee] is status:
                lines.append(f"- {GUARANTEE_TEXT[guarantee]}: {STATUS_TEXT[status]}.")
    tests = "pôde" if config.agent_runs_tests else "não pôde"
    lines += ["", f"O agente {tests} rodar os testes do projeto (`forja agente testar`)."]
    return lines


def _agents(config: RunConfig) -> list[str]:
    """Which CLI and model each role used, and the CLIs that do not hold their role to the rules."""
    roles = [("implementa", config.implementer)]
    if config.test_author:
        roles.append(("escreve os testes", config.test_author))
    lines = [""]
    for role, executor in roles:
        model = f", modelo `{executor.model}`" if executor.model else ""
        lines.append(f"- Quem {role}: `{executor.name}` {executor.version}{model}.")
    lines.append("- Quem documenta: o mesmo que implementa, sem comandos e só em documentação.")
    for role, executor in roles:
        if executor.enforces_permissions is False:
            lines.append(
                f"- Limitação: a CLI `{executor.name}` ({role}) não garante as permissões do "
                "papel. A Forja pediu só leitura, edição de arquivos e os comandos permitidos, "
                "mas a CLI não impede que o agente faça mais; a Forja confere o resultado "
                "(escopo, congelamento dos testes, git antes e depois de cada chamada)."
            )
    return lines


SPECIFIER_STAGE = "c"  # the stage of the specifier is ``<task>-c``; it commits nothing


def _premises(state: RunState, facts: Facts, config: RunConfig) -> list[str]:
    """Each premise with its name, the commits that depend on it and what a person recorded."""
    lines = [_premise_line(state, p, config) for p in facts.premises]
    names = {p.id for p in facts.premises}
    lines += [
        f"- O fato `{f.id}` trata da premissa `{f.premise}`, que esta execução não teve."
        for f in config.facts
        if f.premise and f.premise not in names
    ]
    return lines or ["Nenhuma."]


def _premise_line(state: RunState, premise: Premise, config: RunConfig) -> str:
    if premise.check:
        what = (
            f"{premise.check}: não foi possível medir; a tarefa `{premise.task}` seguiu "
            f"(tentativa `{premise.attempt}`)."
        )
    else:
        what = (
            f"{premise.statement} (por quê: {premise.reason}; evidência que faltou: "
            f"{premise.missing_evidence}); tarefa `{premise.task}`, tentativa `{premise.attempt}`."
        )
    affected = _affected(state, premise)
    commits = (
        "Commits com " + ", ".join(f"`Stage-Id: {s}`" for s in affected) + "."
        if affected
        else "Nenhum commit depende dela."
    )
    settled = [
        f"{'Confirmada' if f.relation == 'confirms' else 'Corrigida'} por `{f.id}` "
        f"({f.author}, {f.date}): {f.text}"
        for f in config.facts
        if f.premise == premise.id
    ]
    return " ".join([f"- `{premise.id}` {what}", commits, *settled])


def _affected(state: RunState, premise: Premise) -> list[str]:
    """The committed stages of the task from the one the premise arose in: what they did rests on
    it. The specifier's stage commits nothing. Tasks do not depend on each other."""
    stages = state.children_of(Level.STAGE, premise.task)
    start = stages.index(premise.stage) if premise.stage in stages else 0
    return [
        stage
        for stage in stages[start:]
        if state.state_of(Level.STAGE, stage) is StageState.COMMITTED
        and stage != f"{premise.task}-{SPECIFIER_STAGE}"
    ]


def _blocked(state: RunState) -> list[str]:
    lines = []
    for task in state.children_of(Level.TASK, state.run_id):
        if state.state_of(Level.TASK, task) is not TaskState.BLOCKED:
            continue
        payload = state.transition_payload(Level.TASK, task, TaskState.BLOCKED) or {}
        reason = payload.get("reason", "motivo não registrado")
        lines.append(f"- `{task}` ({_intent(state, task)}): {reason}")
        lines.extend(_rejections(state, task))
    return lines or ["Nenhuma."]


def _rejections(state: RunState, task: str) -> list[str]:
    lines = []
    for stage in state.children_of(Level.STAGE, task):
        for attempt in state.children_of(Level.ATTEMPT, stage):
            payload = state.transition_payload(Level.ATTEMPT, attempt, AttemptState.REJECTED)
            if payload is not None:
                lines.append(f"  - tentativa `{attempt}` rejeitada: {payload['reason']}")
    return lines


def _refactorings(state: RunState) -> list[str]:
    done = [
        f"- `{o.task_id}`: {_intent(state, o.task_id)} "
        f"({o.attempts} tentativa(s), {o.rejected_attempts} rejeitada(s))"
        for o in task_outcomes(state)
        if o.outcome is TaskOutcomeKind.INTEGRATED
    ]
    return done or ["Nenhuma."]


def _traceability(state: RunState, facts: Facts) -> list[str]:
    """Per integrated task: each criterion, its origin in the input and its tests."""
    lines = []
    for outcome in task_outcomes(state):
        rows = facts.traced.get(outcome.task_id)
        if outcome.outcome is not TaskOutcomeKind.INTEGRATED or not rows:
            continue
        lines.append(f"- `{outcome.task_id}`:")
        for row in rows:
            origin = ", ".join(row.origin)
            tests = ", ".join(f"`{t}`" for t in row.tests) or "nenhum teste"
            lines.append(f"  - critério {row.id} (origem {origin}): {row.text} → {tests}")
    if not lines:
        return ["Nenhuma tarefa integrada com critérios e testes."]
    return [
        *lines,
        "",
        "Conferido: cada critério tem teste que falhava antes do conserto. Não conferido: que o "
        "critério diga o que o elemento da entrada diz, nem que o teste verifique o critério "
        "além do que falhar e passar mostra; isso é da revisão.",
    ]


def _documentation(state: RunState, facts: Facts) -> list[str]:
    """Per integrated task: its record, the README it fixed and the decision records it wrote."""
    lines = []
    for outcome in task_outcomes(state):
        found = facts.documented.get(outcome.task_id)
        if outcome.outcome is not TaskOutcomeKind.INTEGRATED or found is None:
            continue
        readme = [f for f in found.files if f in README_NAMES]
        adrs = [f for f in found.files if f.startswith(ADR_DIR)]
        others = [f for f in found.files if f not in readme and f not in adrs]
        parts = [f"registro `{found.record}`"]
        for label, paths in (("README", readme), ("ADR", adrs), ("outros", others)):
            if paths:
                parts.append(f"{label}: " + ", ".join(f"`{p}`" for p in paths))
        lines.append(f"- `{outcome.task_id}`: " + "; ".join(parts) + ".")
    if not lines:
        return ["Nenhuma tarefa integrada com documentação."]
    return [
        *lines,
        "",
        "Não conferido: links externos do README (exigiriam rede). O texto que o agente "
        "escreveu fora das afirmações com citação só passa pelas verificações de tópico.",
    ]


def _intent(state: RunState, task: str) -> str:
    payload = state.transition_payload(Level.TASK, task, TaskState.PENDING) or {}
    return str(payload.get("intent", ""))


def _metrics(facts: Facts) -> list[str]:
    names = sorted(set(facts.baseline) | set(facts.final))
    if not names:
        return ["Sem medições registradas."]
    rows = ["| Métrica | Antes | Depois |", "| --- | --- | --- |"]
    for name in names:
        rows.append(f"| {name} | {_number(facts.baseline, name)} | {_number(facts.final, name)} |")
    return rows


def _number(values: Mapping[str, float], name: str) -> str:
    return f"{values[name]:g}" if name in values else "-"
