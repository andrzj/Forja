"""Reading what Maven, Spotless, Checkstyle, PMD, SpotBugs and Surefire leave behind.

Every parser works from the text of the log and never raises: a line it does not understand is
skipped, and output it cannot make sense of at all is ``Unparseable``, which the gate turns into an
inconclusive result instead of a pass. Surefire, PMD and SpotBugs write XML reports under
``target`` instead of printing their findings; those are read from the directory the command ran
in (``ToolOutput.root``), and the command starts with ``clean`` so no report is left over from an
earlier run. Paths are made relative to that directory.
"""

import re
from collections import Counter
from collections.abc import Iterator
from pathlib import Path, PurePosixPath
from xml.etree.ElementTree import Element

from forja.core.adapters import EvidenceDraft, Parsed, ParseResult, ToolOutput, Unparseable
from forja.core.adapters.common import read_output_lines
from forja.core.evidence import Target, TargetKind
from forja.core.reports.reading import ReportError, load_xml

MAX_LINE = 100_000  # a test name can be long; beyond this the line is not ours
MAX_REPORT = 20_000_000  # a report larger than this is not one a build writes

_SPOTLESS_FILE = re.compile(r"^\[ERROR\] {5}(?P<path>\S.*\.java)\s*$")
_CHECKSTYLE = re.compile(
    r"^\[(?:WARN|WARNING|ERROR)\]\s+(?P<path>.+?\.java):\d+(?::\d+)?: .*\[(?P<rule>\w+)\]\s*$"
)
_COMPILE_ERROR = re.compile(r"^\[ERROR\]\s+(?P<path>.+?\.java):\[\d+,\d+\] ")
_OK = (0, 1)


def _lines(output: ToolOutput) -> list[str]:
    return [line for line in read_output_lines(output.log_path) if len(line) <= MAX_LINE]


def _path(text: str, output: ToolOutput) -> str:
    """The path as the repository knows it: POSIX, and relative to where the command ran."""
    posix = re.sub(r"^/(?=[A-Za-z]:/)", "", text.strip().replace("\\", "/"))  # Maven: /C:/dir
    root = output.root.as_posix().rstrip("/") + "/" if output.root is not None else ""
    if root and posix.startswith(root):
        posix = posix[len(root) :]
    elif PurePosixPath(posix).is_absolute() or re.match(r"^[A-Za-z]:/", posix):
        posix = posix.rsplit("/", 1)[-1]  # outside the repository: only the name is ours to say
    return posix.removeprefix("./")


def _draft(
    measurement: str, kind: TargetKind, target: str, value: bool | int | float | str, unit: str
) -> EvidenceDraft:
    return EvidenceDraft(measurement, Target(kind=kind, id=target), value, unit)


def _each(tree: Element, name: str) -> Iterator[Element]:
    """The elements called ``name`` in any namespace (PMD declares one)."""
    return (element for element in tree.iter() if element.tag.rsplit("}", 1)[-1] == name)


def _reports(output: ToolOutput, pattern: str) -> list[Path]:
    """The report files the command wrote, regular files only and under the directory it ran in."""
    if output.root is None:
        return []
    inside = output.root.resolve()
    return sorted(
        path
        for path in output.root.glob(pattern)
        if path.is_file()
        and not path.is_symlink()
        and path.stat().st_size <= MAX_REPORT
        and path.resolve().is_relative_to(inside)
    )


def parse_format(output: ToolOutput) -> ParseResult:
    """The files Spotless says are not in the form google-java-format writes."""
    if output.exit_code not in _OK:
        return Unparseable(f"spotless ended with {output.exit_code}")
    files = sorted(
        {
            _path(found["path"], output)
            for found in map(_SPOTLESS_FILE.match, _lines(output))
            if found
        }
    )
    if output.exit_code == 1 and not files:
        return Unparseable("spotless failed in a form this parser does not know")
    return Parsed(
        tuple(_draft("format.unformatted", TargetKind.FILE, path, 1, "files") for path in files)
    )


def _checkstyle(output: ToolOutput) -> Counter[tuple[str, str]]:
    counts: Counter[tuple[str, str]] = Counter()
    for line in _lines(output):
        found = _CHECKSTYLE.match(line.strip())
        if found:
            counts[(_path(found["path"], output), f"checkstyle.{found['rule']}")] += 1
    return counts


def _pmd(output: ToolOutput) -> Counter[tuple[str, str]]:
    counts: Counter[tuple[str, str]] = Counter()
    for report in _reports(output, "target/pmd.xml"):
        for file in _each(load_xml(report.read_text(encoding="utf-8")), "file"):
            path = _path(file.get("name", ""), output)
            for violation in _each(file, "violation"):
                counts[(path, f"pmd.{violation.get('rule', 'violation')}")] += 1
    return counts


def _spotbugs(output: ToolOutput) -> Counter[tuple[str, str]]:
    counts: Counter[tuple[str, str]] = Counter()
    for report in _reports(output, "target/spotbugsXml.xml"):
        tree = load_xml(report.read_text(encoding="utf-8"))
        for bug in tree.iter("BugInstance"):
            where = next((s for s in bug.iter("SourceLine") if s.get("sourcepath")), None)
            if where is None:
                continue
            path = _source_path(output, where.get("sourcepath", ""))
            counts[(path, f"spotbugs.{bug.get('type', 'bug')}")] += 1
    return counts


def _source_path(output: ToolOutput, sourcepath: str) -> str:
    """SpotBugs says ``com/acme/Calc.java``; the file is under the source root that holds it."""
    if output.root is not None:
        for source_root in ("src/main/java", "src/test/java"):
            if (output.root / source_root / sourcepath).is_file():
                return f"{source_root}/{sourcepath}"
    return sourcepath


def parse_lint(output: ToolOutput) -> ParseResult:
    """Findings per file and rule of Checkstyle (the log), PMD and SpotBugs (their reports)."""
    if output.exit_code not in _OK:
        return Unparseable(f"maven ended with {output.exit_code}")
    try:
        counts = _checkstyle(output) + _pmd(output) + _spotbugs(output)
    except (OSError, ReportError) as error:
        return Unparseable(f"a lint report cannot be read ({error})")
    if output.exit_code == 1 and not counts:
        return Unparseable("maven failed in a form this parser does not know")
    return Parsed(
        tuple(
            _draft(f"lint.{rule}", TargetKind.FILE, path, count, "violations")
            for (path, rule), count in sorted(counts.items())
        )
    )


def parse_build(output: ToolOutput) -> ParseResult:
    """The files ``javac`` could not compile."""
    if output.exit_code is None:
        return Unparseable("maven did not finish")
    if output.exit_code == 0:
        return Parsed(())
    paths = sorted(
        {_path(m["path"], output) for m in map(_COMPILE_ERROR.match, _lines(output)) if m}
    )
    if not paths:
        return Parsed((_draft("build.failed", TargetKind.MODULE, "build", 1, "failures"),))
    return Parsed(
        tuple(_draft("build.compile_error", TargetKind.FILE, path, 1, "errors") for path in paths)
    )


def parse_tests(output: ToolOutput) -> ParseResult:
    """Outcome of every test case in the Surefire reports."""
    code = output.exit_code
    if code not in _OK:
        return Unparseable(f"maven ended with {code}")
    outcomes: dict[str, str] = {}
    try:
        for report in _reports(output, "**/target/surefire-reports/TEST-*.xml"):
            for case in load_xml(report.read_text(encoding="utf-8")).iter("testcase"):
                name = f"{case.get('classname', '')}.{case.get('name', '')}".strip(".")
                if case.find("failure") is not None or case.find("error") is not None:
                    outcomes[name] = "failed"
                elif case.find("skipped") is not None:
                    outcomes[name] = "skipped"
                else:
                    outcomes[name] = "passed"
    except (OSError, ReportError) as error:
        return Unparseable(f"a test report cannot be read ({error})")
    failed = any(o == "failed" for o in outcomes.values())
    if code == 1 and not failed:
        return Unparseable("maven reported a failure in a form this parser does not know")
    if code == 0 and failed:
        return Unparseable("maven passed but its reports list failures")
    if not outcomes:
        return Parsed((_draft("test.collected", TargetKind.MODULE, "tests", 0, "tests"),))
    drafts = [
        _draft("test.outcome", TargetKind.SYMBOL, test_id, outcome, "outcome")
        for test_id, outcome in sorted(outcomes.items())
    ]
    skipped = sum(1 for o in outcomes.values() if o == "skipped")
    if skipped:
        drafts.append(_draft("test.skipped", TargetKind.MODULE, "tests", skipped, "tests"))
    return Parsed(tuple(drafts))
