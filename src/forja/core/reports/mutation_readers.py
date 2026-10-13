"""Readers of the native mutation reports. Each answers a ``MutationReport``.

Tools disagree on statuses; the mapping is the same everywhere. A mutant that a test noticed is
``KILLED`` (a crash or a compile-time failure counts: the change was caught, though not by a
test's judgment). One that never ran is ``UNCOVERED``. One the tool could not even build, or did
not judge, is left out or reported as an error: it says nothing about the tests.
"""

from collections.abc import Sequence
from pathlib import Path

from forja.core.reports.models import MutantResult, MutantStatus, MutationReport
from forja.core.reports.reading import ReportError, load_json, load_xml, number, resolve_path

_MAX_CHANGE = 80

# PIT: NON_VIABLE (does not compile) says nothing about the tests; the others never ran or
# were not judged
_PIT = {
    "KILLED": MutantStatus.KILLED,
    "SURVIVED": MutantStatus.SURVIVED,
    "NO_COVERAGE": MutantStatus.UNCOVERED,
    "TIMED_OUT": MutantStatus.TIMEOUT,
    "MEMORY_ERROR": MutantStatus.TIMEOUT,
}
_PIT_SKIPPED = {"NON_VIABLE"}

_GREMLINS = {
    "KILLED": MutantStatus.KILLED,
    "LIVED": MutantStatus.SURVIVED,
    "NOT COVERED": MutantStatus.UNCOVERED,
    "TIMED OUT": MutantStatus.TIMEOUT,
}
_GREMLINS_SKIPPED = {"NOT VIABLE"}

_STRYKER = {
    "Killed": MutantStatus.KILLED,
    "Survived": MutantStatus.SURVIVED,
    "NoCoverage": MutantStatus.UNCOVERED,
    "Timeout": MutantStatus.TIMEOUT,
    "RuntimeError": MutantStatus.KILLED,
}
_STRYKER_SKIPPED = {"CompileError", "Ignored"}


def _short(text: str) -> str:
    one_line = " ".join(text.split())
    return one_line if len(one_line) <= _MAX_CHANGE else one_line[: _MAX_CHANGE - 1] + "…"


def read_pit_xml(text: str, root: Path, source_roots: Sequence[str] = ()) -> MutationReport:
    """PIT ``mutations.xml``: one ``<mutation status=...>`` per mutant."""
    tree = load_xml(text)
    if tree.tag != "mutations":
        raise ReportError("PIT XML must start with <mutations>")
    found: list[MutantResult] = []
    for mutation in tree.iter("mutation"):
        status = mutation.get("status", "")
        if status in _PIT_SKIPPED:
            continue
        if status not in _PIT:
            raise ReportError(f"PIT: a mutant that was not judged ({status or 'no status'})")
        cls = (mutation.findtext("mutatedClass") or "").strip()
        source = (mutation.findtext("sourceFile") or "").strip()
        if not cls or not source:
            raise ReportError("PIT: a mutation without class or source file")
        package = cls.rsplit(".", 1)[0].replace(".", "/") if "." in cls else ""
        path = resolve_path(f"{package}/{source}".strip("/"), root, source_roots)
        description = (mutation.findtext("description") or "").strip()
        mutator = (mutation.findtext("mutator") or "").rsplit(".", 1)[-1]
        found.append(
            MutantResult(
                path,
                number(mutation.findtext("lineNumber"), "lineNumber"),
                _short(description or mutator or "mutation"),
                _PIT[status],
                function=(mutation.findtext("mutatedMethod") or None),
            )
        )
    return MutationReport(tuple(found))


def read_gremlins_json(text: str, root: Path, source_roots: Sequence[str] = ()) -> MutationReport:
    """gremlins ``--output``: ``files[].mutations[]`` with a type and a status."""
    document = load_json(text)
    files = document.get("files") if isinstance(document, dict) else None
    if not isinstance(files, list):
        raise ReportError("gremlins JSON without a 'files' list")
    found: list[MutantResult] = []
    for file in files:
        path = resolve_path(file["file_name"], root, source_roots)
        for mutation in file["mutations"]:
            status = mutation["status"]
            if status in _GREMLINS_SKIPPED:
                continue
            if status not in _GREMLINS:
                raise ReportError(f"gremlins: a mutant that was not judged ({status!r})")
            found.append(
                MutantResult(
                    path,
                    number(mutation["line"], "line"),
                    _short(str(mutation["type"]).lower().replace("_", " ")),
                    _GREMLINS[status],
                )
            )
    return MutationReport(tuple(found))


def read_stryker_json(text: str, root: Path, source_roots: Sequence[str] = ()) -> MutationReport:
    """The mutation-testing-elements report that StrykerJS and Stryker.NET write."""
    document = load_json(text)
    files = document.get("files") if isinstance(document, dict) else None
    if not isinstance(files, dict):
        raise ReportError("Stryker JSON without a 'files' object")
    found: list[MutantResult] = []
    for raw, data in files.items():
        path = resolve_path(raw, root, source_roots)
        for mutant in data["mutants"]:
            status = mutant["status"]
            if status in _STRYKER_SKIPPED:
                continue
            if status not in _STRYKER:
                raise ReportError(f"Stryker: a mutant that was not judged ({status!r})")
            change = f"{mutant['mutatorName']}: {mutant.get('replacement', '')}".rstrip(": ")
            found.append(
                MutantResult(
                    path,
                    number(mutant["location"]["start"]["line"], "line"),
                    _short(change),
                    _STRYKER[status],
                )
            )
    return MutationReport(tuple(found))
