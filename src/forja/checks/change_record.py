"""The change record of a task (increment 4): the facts the Forja measures, and nothing else.

The factual part is generated here and compared again by the gate, so the model cannot change it.
The section the model contributes, why and impact, is built only from claims that carry a
citation. A removed symbol comes with the proof that nothing else mentions it, or with the files
that still do, and a removed public symbol is flagged.
"""

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from forja.checks.changes import Change, Changes
from forja.checks.structure import dialect_of
from forja.checks.symbols import Symbol, symbols_in
from forja.core.artifacts.llm_output import (
    Citation,
    Claim,
    DeclaredChange,
    EvidenceCitation,
    FactCitation,
    FileCitation,
)
from forja.core.artifacts.models import Assumption, Executor
from forja.core.artifacts.schemas import (
    ChangeRecordBody,
    RecordedFile,
    RecordedSymbol,
    ToolVersion,
)

MAX_REFERENCES = 5
REASONS = "## Porquê e impacto"
SECTIONS = (
    "## Arquivos",
    "## Símbolos",
    "## Métricas",
    "## Gates aprovados",
    "## Ferramentas",
    "## Premissas",
    "## Para reverter",
    REASONS,
)
CHANGES_DIR = "docs/mudancas"
NONE = "Nenhum."


@dataclass(frozen=True)
class SymbolChange:
    path: str
    name: str
    kind: str
    change: DeclaredChange
    public: bool
    proof: str = ""  # only for a removal: who still mentions the name, or that nobody does


@dataclass(frozen=True)
class RecordFacts:
    task_id: str
    intent: str
    files: tuple[RecordedFile, ...]
    symbols: tuple[SymbolChange, ...]
    metrics_before: Mapping[str, float]
    metrics_after: Mapping[str, float]
    gates_passed: tuple[str, ...]
    toolchains: tuple[ToolVersion, ...]
    executors: tuple[Executor, ...]
    revert_commit: str
    assumptions: tuple[Assumption, ...] = ()
    unreadable: tuple[str, ...] = ()  # source files whose symbols could not be listed


def record_path(task_id: str) -> str:
    """Where the record of a task lives in the repository."""
    return f"{CHANGES_DIR}/{task_id}.md"


def file_changes(changes: Changes) -> tuple[RecordedFile, ...]:
    """Every file the task touched, as the record lists them."""
    recorded = []
    for change in changes.files:
        if change.kind.value == "A":
            kind = DeclaredChange.CREATED
        elif change.kind.value == "D":
            kind = DeclaredChange.REMOVED
        else:
            kind = DeclaredChange.MODIFIED
        recorded.append(RecordedFile(path=change.path, change=kind))
    return tuple(sorted(recorded, key=lambda f: f.path))


def symbol_changes(
    changes: Changes,
    before: Mapping[str, str],
    worktree: Path,
    others: Mapping[str, str],
) -> tuple[tuple[SymbolChange, ...], tuple[str, ...]]:
    """The symbols created, changed or removed, and the source files that could not be read.

    ``before`` is the parent commit's text by old path; ``others`` is the text of the files the
    task did not remove, used to prove that a removed symbol is no longer used.
    """
    found: list[SymbolChange] = []
    unreadable: list[str] = []
    for change in changes.files:
        if dialect_of(change.path) is None and dialect_of(change.before or "") is None:
            continue
        old = _symbols(change.before, before.get(change.before or ""))
        new = _symbols(change.path, _read(worktree / change.path)) if change.exists_now else {}
        if old is None or new is None:
            unreadable.append(change.path)
            continue
        found += _compare(change, old, new, others)
    return tuple(sorted(found, key=lambda s: (s.path, s.name, s.change.value))), tuple(
        sorted(unreadable)
    )


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _symbols(path: str | None, source: str | None) -> dict[str, Symbol] | None:
    """The symbols by name; empty for a file that did not exist, ``None`` when unreadable."""
    if path is None:
        return {}
    if source is None:
        return None
    listed = symbols_in(path, source)
    return None if listed is None else {s.name: s for s in listed}


def _compare(
    change: Change, old: dict[str, Symbol], new: dict[str, Symbol], others: Mapping[str, str]
) -> list[SymbolChange]:
    found = []
    for name in sorted(old.keys() | new.keys()):
        was, now = old.get(name), new.get(name)
        if was is None and now is not None:
            found.append(
                SymbolChange(change.path, name, now.kind, DeclaredChange.CREATED, now.public)
            )
        elif was is not None and now is None:
            proof = reference_proof(name, change.path, others)
            found.append(
                SymbolChange(change.path, name, was.kind, DeclaredChange.REMOVED, was.public, proof)
            )
        elif was is not None and now is not None and was.shape != now.shape:
            found.append(
                SymbolChange(change.path, name, now.kind, DeclaredChange.MODIFIED, now.public)
            )
    return found


def reference_proof(name: str, own: str, others: Mapping[str, str]) -> str:
    """Whether any file but ``own`` still mentions the last part of ``name`` as a whole word."""
    word = re.compile(rf"(?<![\w]){re.escape(name.rsplit('.', 1)[-1])}(?![\w])")
    mentioning = sorted(
        path for path, content in others.items() if path != own and word.search(content)
    )
    if not mentioning:
        return "nenhum outro arquivo menciona o nome"
    shown = ", ".join(f"`{p}`" for p in mentioning[:MAX_REFERENCES])
    more = f" e mais {len(mentioning) - MAX_REFERENCES}" if len(mentioning) > MAX_REFERENCES else ""
    return f"ainda mencionado em {shown}{more}"


def to_body(facts: RecordFacts) -> ChangeRecordBody:
    return ChangeRecordBody(
        files=facts.files,
        symbols=tuple(
            RecordedSymbol(path=s.path, name=s.name, kind=s.kind, change=s.change)
            for s in facts.symbols
        ),
        evidence_before=_metrics(facts.metrics_before),
        evidence_after=_metrics(facts.metrics_after),
        gates_passed=facts.gates_passed,
        toolchains=facts.toolchains,
        executors=facts.executors,
        revert_commit=facts.revert_commit,
    )


def _metrics(values: Mapping[str, float]) -> tuple[str, ...]:
    return tuple(f"{name}={values[name]:g}" for name in sorted(values))


def render_changed(
    files: Sequence[RecordedFile], symbols: Sequence[SymbolChange], unreadable: Sequence[str]
) -> str:
    """The two sections that follow from the task's diff alone: files and symbols. The gate
    renders them again from the diff and looks for them in the record."""
    lines = [
        "## Arquivos",
        "",
        *_list(f"`{f.path}`: {f.change.value}" for f in sorted(files, key=_path)),
        "",
    ]
    lines += ["## Símbolos", "", *_list(_symbol_line(s) for s in sorted(symbols, key=_place))]
    if unreadable:
        lines += [
            "",
            "Símbolos não listados (arquivo ilegível):",
            *_list(f"`{p}`" for p in unreadable),
        ]
    return "\n".join(lines)


def render_facts(facts: RecordFacts) -> str:
    """The part of the record that only the Forja writes; the gate renders it again to compare."""
    lines = [f"# Registro de mudança: {facts.task_id}", "", facts.intent, ""]
    lines += [render_changed(facts.files, facts.symbols, facts.unreadable)]
    lines += ["", "## Métricas", "", *_metric_table(facts), ""]
    lines += ["## Gates aprovados", "", *_list(sorted(facts.gates_passed)), ""]
    lines += ["## Ferramentas", "", *_list(f"{t.name} {t.version}" for t in facts.toolchains)]
    lines += [*_list(f"CLI {e.cli} {e.version}" for e in facts.executors), ""]
    lines += ["## Premissas", "", *_list(_premise_line(a) for a in facts.assumptions), ""]
    lines += ["## Para reverter", "", f"`git revert {facts.revert_commit}`", ""]
    return "\n".join(lines)


def _path(file: RecordedFile) -> str:
    return file.path


def _place(symbol: SymbolChange) -> tuple[str, str, str]:
    return symbol.path, symbol.name, symbol.change.value


def _list(items: Iterable[str]) -> list[str]:
    rows = [f"- {item}" for item in items]
    return rows or [NONE]


def _symbol_line(symbol: SymbolChange) -> str:
    line = f"`{symbol.name}` ({symbol.kind}) em `{symbol.path}`: {symbol.change.value}"
    if symbol.change is DeclaredChange.REMOVED:
        flag = " **símbolo público removido.**" if symbol.public else ""
        line += f";{flag} prova de não uso: {symbol.proof}"
    return line


def _metric_table(facts: RecordFacts) -> list[str]:
    names = sorted(facts.metrics_before.keys() | facts.metrics_after.keys())
    if not names:
        return [NONE]
    rows = ["| Métrica | Antes | Depois |", "| --- | --- | --- |"]
    for name in names:
        before, after = facts.metrics_before.get(name), facts.metrics_after.get(name)
        rows.append(f"| {name} | {_num(before)} | {_num(after)} |")
    return rows


def _num(value: float | None) -> str:
    return "-" if value is None else f"{value:g}"


def _premise_line(assumption: Assumption) -> str:
    why = f"motivo: {assumption.reason}; faltou: {assumption.missing_evidence}"
    return f"{assumption.statement} ({why})"


def render_record(facts: RecordFacts, claims: Sequence[Claim]) -> str:
    """The whole record: the facts, then why and impact, each sentence with its citation."""
    return "\n".join([render_facts(facts), REASONS, "", *_claims(claims), ""])


def _claims(claims: Sequence[Claim]) -> list[str]:
    return [f"- {c.statement} ({'; '.join(_cite(x) for x in c.citations)})" for c in claims] or [
        NONE
    ]


def _cite(citation: Citation) -> str:
    if isinstance(citation, FileCitation):
        return f"`{citation.path}:{citation.line_start}-{citation.line_end}`"
    if isinstance(citation, EvidenceCitation):
        return f"evidência {citation.evidence_id}"
    assert isinstance(citation, FactCitation)
    return f"fato {citation.fact_id}"
