"""What the two opposing meters share: reading the shape of the files an attempt changed."""

from pathlib import Path

from forja.checks.structure import Module, SyntaxProblem, analyze, dialect_of
from forja.core.gates import GateInput, Inconclusive
from forja.core.gates.models import InconclusiveReason


def threshold(data: GateInput, language: str, name: str, default: float) -> float:
    """A positive number the policy sets for ``language``, or ``default``."""
    thresholds = data.values.get("thresholds")
    per_language = thresholds.get(language) if isinstance(thresholds, dict) else None
    value = per_language.get(name) if isinstance(per_language, dict) else None
    if isinstance(value, bool) or not isinstance(value, int | float) or value <= 0:
        return default
    return float(value)


def language_of(path: str) -> str:
    dialect = dialect_of(path)
    return dialect.language if dialect is not None else ""


def shapes(texts: dict[str, str]) -> dict[str, Module]:
    """The shape of each file in a language Forja reads; the others are left out."""
    found = {}
    for path, source in texts.items():
        module = analyze(path, source)
        if module is not None:
            found[path] = module
    return found


def read_texts(root: Path, files: tuple[str, ...]) -> dict[str, str]:
    texts = {}
    for path in files:
        if dialect_of(path) is not None and (root / path).is_file():
            texts[path] = (root / path).read_text(encoding="utf-8", errors="replace")
    return texts


def unreadable(problem: SyntaxProblem) -> Inconclusive:
    return Inconclusive(reason=InconclusiveReason.UNSUPPORTED_CONSTRUCT, detail=str(problem))


def shapes_before(before: dict[str, str]) -> dict[str, Module]:
    """The parent commit's shapes; a file that did not parse then has nothing to compare with."""
    found = {}
    for path, source in before.items():
        try:
            found.update(shapes({path: source}))
        except SyntaxProblem:
            continue
    return found
