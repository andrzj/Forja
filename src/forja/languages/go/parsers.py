"""Reading what gofmt, golangci-lint, ``go build`` and ``go test -json`` print.

Every parser works from the text of the log and never raises: a line it does not understand is
skipped, and output it cannot make sense of at all is ``Unparseable``, which the gate turns into an
inconclusive result instead of a pass.
"""

import json
import re
from collections import Counter

from forja.core.adapters import EvidenceDraft, Parsed, ParseResult, ToolOutput, Unparseable
from forja.core.adapters.common import read_output_lines
from forja.core.evidence import Target, TargetKind

MAX_LINE = 100_000  # a test event can carry a long line of output; beyond this it is not ours

_POSITION = r"(?P<path>[^\s:][^:]*\.go):\d+(?::\d+)?"
_GOFMT_ERROR = re.compile(rf"^{_POSITION}: ")
_BUILD_ERROR = re.compile(rf"^{_POSITION}: ")
_LINT_LINE = re.compile(rf"^{_POSITION}: .*\((?P<linter>[A-Za-z0-9_-]+)\)$")
_LINT_OK = (0, 1)
_OUTCOMES = {"pass": "passed", "fail": "failed", "skip": "skipped"}


def _lines(output: ToolOutput) -> list[str]:
    return [line for line in read_output_lines(output.log_path) if len(line) <= MAX_LINE]


def _path(text: str) -> str:
    return text.strip().replace("\\\\", "/").replace("\\", "/").removeprefix("./")


def _draft(
    measurement: str, kind: TargetKind, target: str, value: bool | int | float | str, unit: str
) -> EvidenceDraft:
    return EvidenceDraft(measurement, Target(kind=kind, id=target), value, unit)


def parse_format(output: ToolOutput) -> ParseResult:
    """Files ``gofmt -l`` lists (not in canonical form) and files it could not read."""
    if output.exit_code not in (0, 2):
        return Unparseable(f"gofmt ended with {output.exit_code}")
    drafts: dict[tuple[str, str], EvidenceDraft] = {}
    for line in _lines(output):
        text = line.strip()
        broken = _GOFMT_ERROR.match(text)
        if broken:
            name = "format.invalid_syntax"
            path = _path(broken["path"])
        elif text.endswith(".go") and ":" not in text.replace("\\", "/").split("/")[-1]:
            name, path = "format.unformatted", _path(text)
        else:
            continue
        drafts[(name, path)] = _draft(name, TargetKind.FILE, path, 1, "files")
    if output.exit_code == 2 and not drafts:
        return Unparseable("gofmt failed in a form this parser does not know")
    return Parsed(tuple(drafts[key] for key in sorted(drafts)))


def parse_lint(output: ToolOutput) -> ParseResult:
    """Findings per file and linter (golangci-lint's ``path:line:col: message (linter)``)."""
    if output.exit_code not in _LINT_OK:
        return Unparseable(f"golangci-lint ended with {output.exit_code}")
    counts: Counter[tuple[str, str]] = Counter()
    for line in _lines(output):
        found = _LINT_LINE.match(line.strip())
        if found:
            counts[(_path(found["path"]), found["linter"])] += 1
    if output.exit_code == 1 and not counts:
        return Unparseable("golangci-lint reported issues in a form this parser does not know")
    return Parsed(
        tuple(
            _draft(f"lint.{linter}", TargetKind.FILE, path, count, "violations")
            for (path, linter), count in sorted(counts.items())
        )
    )


def parse_build(output: ToolOutput) -> ParseResult:
    """The files ``go build`` could not compile."""
    if output.exit_code is None:
        return Unparseable("go build did not finish")
    if output.exit_code == 0:
        return Parsed(())
    paths = sorted({_path(m["path"]) for m in map(_BUILD_ERROR.match, _lines(output)) if m})
    if not paths:
        return Parsed((_draft("build.failed", TargetKind.MODULE, "build", 1, "failures"),))
    return Parsed(
        tuple(_draft("build.compile_error", TargetKind.FILE, path, 1, "errors") for path in paths)
    )


def _events(lines: list[str]) -> list[dict[str, object]]:
    events = []
    for line in lines:
        if not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict):
            events.append(event)
    return events


def parse_tests(output: ToolOutput) -> ParseResult:
    """Outcome of every test (``go test -json``), and how many were skipped.

    A package that fails with no failed test (it did not compile, or crashed) is one failed
    outcome of its own, so the failure is never lost.
    """
    code = output.exit_code
    if code not in (0, 1):
        return Unparseable(f"go test ended with {code}")
    outcomes: dict[str, str] = {}
    packages: dict[str, str] = {}
    failed_in: set[str] = set()
    for event in _events(_lines(output)):
        action, package, test = event.get("Action"), event.get("Package"), event.get("Test")
        if action not in _OUTCOMES or not isinstance(package, str):
            continue
        if isinstance(test, str):
            outcomes[f"{package}/{test}"] = _OUTCOMES[str(action)]
            if action == "fail":
                failed_in.add(package)
        else:
            packages[package] = _OUTCOMES[str(action)]
    for package, outcome in packages.items():
        if outcome == "failed" and package not in failed_in:
            outcomes[package] = "failed"
    failed = any(o == "failed" for o in outcomes.values())
    if code == 1 and not failed:
        return Unparseable("go test reported a failure in a form this parser does not know")
    if code == 0 and failed:
        return Unparseable("go test passed but its output lists failures")
    if not outcomes:
        if code == 1 or not packages:
            return Unparseable("go test printed no test events")
        return Parsed((_draft("test.collected", TargetKind.MODULE, "tests", 0, "tests"),))
    drafts = [
        _draft("test.outcome", TargetKind.SYMBOL, test_id, outcome, "outcome")
        for test_id, outcome in sorted(outcomes.items())
    ]
    skipped = sum(1 for o in outcomes.values() if o == "skipped")
    if skipped:
        drafts.append(_draft("test.skipped", TargetKind.MODULE, "tests", skipped, "tests"))
    return Parsed(tuple(drafts))
