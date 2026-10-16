"""Which native report a tool writes, so one reader per format serves every language.

A language adapter says *where* and *in what format* its coverage tool writes; the
core runs the command and hands the file to the reader for that format. Adapters stay pure.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from forja.core.adapters.common import NotSupported
from forja.core.adapters.language import Operation
from forja.core.artifacts.llm_output import check_relative_path


class ReportFormat(StrEnum):
    COVERAGE_PY_JSON = "coverage_py_json"  # Python: coverage.py (json, with contexts)
    JACOCO_XML = "jacoco_xml"  # Java: JaCoCo
    GO_COVERPROFILE = "go_coverprofile"  # Go: go test -coverprofile
    COBERTURA_XML = "cobertura_xml"  # C#: coverlet
    ISTANBUL_JSON = "istanbul_json"  # JavaScript and TypeScript: c8 or istanbul


COVERAGE_FORMATS = frozenset(
    {
        ReportFormat.COVERAGE_PY_JSON,
        ReportFormat.JACOCO_XML,
        ReportFormat.GO_COVERPROFILE,
        ReportFormat.COBERTURA_XML,
        ReportFormat.ISTANBUL_JSON,
    }
)


def formats_of(operation: Operation) -> frozenset[ReportFormat]:
    """The formats that make sense as the report of an operation; empty for the others."""
    if operation is Operation.COVERAGE:
        return COVERAGE_FORMATS
    return frozenset()


@dataclass(frozen=True)
class ReportSpec:
    """The report a command leaves behind: its format and its repository-relative POSIX path."""

    format: ReportFormat
    path: str

    def __post_init__(self) -> None:
        check_relative_path(self.path)


class ReportingAdapter(Protocol):
    """A language adapter that runs coverage also says what it writes."""

    def report(self, operation: Operation) -> ReportSpec | NotSupported: ...
