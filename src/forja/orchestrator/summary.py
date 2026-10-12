"""The summary of an execution: what the reviewer reads before the branch.

Written in Portuguese, to a file in the run directory and never into the repository. The numbers
come from the log, so a resumed run produces the same text as one that was never interrupted.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from forja.core.artifacts.schemas import ExecutionSummaryBody, TaskOutcome, TaskOutcomeKind
from forja.core.confirmation import ConfirmationError, load_confirmation
from forja.core.events.state import RunState
from forja.core.events.versioning import BadLine, parse_line
from forja.core.isolation import Context, Guarantee, Status
from forja.core.states import AttemptState, Level, TaskState
from forja.orchestrator.config import RunConfig

METRICS = "metrics"
PREMISE = "premise"
NOT_APPLICABLE = "Não se aplica nesta versão."


@dataclass(frozen=True)
class Premise:
    task: str
    attempt: str
    check: str


@dataclass
class Facts:
    """What the log says that the states alone do not: assumptions and the measured numbers."""

    premises: list[Premise] = field(default_factory=list)
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
                str(payload.get("task")), str(payload.get("attempt")), str(payload.get("check"))
            )
            if premise not in seen:
                seen.add(premise)
                facts.premises.append(premise)
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
    state: RunState, facts: Facts, config: RunConfig, run_branch: str, summary_path: Path
) -> str:
    lines = [
        f"# Resumo da execução {state.run_id}",
        "",
        f"Branch da entrega: `{run_branch}`, criada a partir de `{config.base_commit[:12]}`.",
        "",
        "## Premissas assumidas",
        "",
        *_premises(facts),
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
        "## Documentação",
        "",
        NOT_APPLICABLE,
        "",
        "## Métricas antes e depois",
        "",
        *_metrics(facts),
        "",
        "## Ambiente e garantias",
        "",
        *_environment(state, config),
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


def _premises(facts: Facts) -> list[str]:
    if not facts.premises:
        return ["Nenhuma."]
    return [
        f"- {p.check}: não foi possível medir; a tarefa `{p.task}` seguiu "
        f"(tentativa `{p.attempt}`)."
        for p in facts.premises
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
