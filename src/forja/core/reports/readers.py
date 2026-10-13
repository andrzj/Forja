"""One entry point per kind of report: pick the reader by format, and fail only with
``ReportError``, whatever the file holds."""

from collections.abc import Callable, Sequence
from pathlib import Path

from forja.core.reports.coverage_readers import (
    read_cobertura_xml,
    read_coverage_py_json,
    read_go_coverprofile,
    read_istanbul_json,
    read_jacoco_xml,
)
from forja.core.reports.formats import ReportFormat
from forja.core.reports.models import CoverageReport, MutationReport
from forja.core.reports.mutation_readers import (
    read_gremlins_json,
    read_pit_xml,
    read_stryker_json,
)
from forja.core.reports.reading import ReportError

_COVERAGE: dict[ReportFormat, Callable[[str, Path, Sequence[str]], CoverageReport]] = {
    ReportFormat.COVERAGE_PY_JSON: read_coverage_py_json,
    ReportFormat.JACOCO_XML: read_jacoco_xml,
    ReportFormat.GO_COVERPROFILE: read_go_coverprofile,
    ReportFormat.COBERTURA_XML: read_cobertura_xml,
    ReportFormat.ISTANBUL_JSON: read_istanbul_json,
}
_MUTATION: dict[ReportFormat, Callable[[str, Path, Sequence[str]], MutationReport]] = {
    ReportFormat.PIT_XML: read_pit_xml,
    ReportFormat.GREMLINS_JSON: read_gremlins_json,
    ReportFormat.STRYKER_JSON: read_stryker_json,
}


def _guarded[T](
    report_format: ReportFormat,
    reader: Callable[[str, Path, Sequence[str]], T],
    text: str,
    root: Path,
    source_roots: Sequence[str],
) -> T:
    try:
        return reader(text, root, source_roots)
    except ReportError:
        raise
    except (ValueError, KeyError, TypeError, AttributeError, IndexError) as error:
        # the file's content is not trusted: a model that refuses it is a bad report, not a bug
        raise ReportError(f"a {report_format.value} report that does not hold: {error}") from None


def read_coverage(
    report_format: ReportFormat, text: str, root: Path, source_roots: Sequence[str] = ()
) -> CoverageReport:
    reader = _COVERAGE.get(report_format)
    if reader is None:
        raise ReportError(f"{report_format.value} is not a coverage format")
    return _guarded(report_format, reader, text, root, source_roots)


def read_mutation(
    report_format: ReportFormat, text: str, root: Path, source_roots: Sequence[str] = ()
) -> MutationReport:
    reader = _MUTATION.get(report_format)
    if reader is None:
        raise ReportError(f"{report_format.value} is not a mutation format")
    return _guarded(report_format, reader, text, root, source_roots)
