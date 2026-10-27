"""The cases of gate 11 (differential test) a repository declares: a command to run on the old and
the new version and what of its output to compare, and by which rule.

Same shape as the other sections: validated as a whole, cases of every layer add up in the order
they were read, and the section is part of the digest only when it exists.
"""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import PurePath
from typing import Any

from forja.core.artifacts.llm_output import check_relative_path

STDOUT = "stdout"
EXIT_CODE = "exit_code"
FILE = "file"
KINDS = (STDOUT, EXIT_CODE, FILE)
BYTES = "bytes"
JSON = "json"
IGNORE = "ignore"
RULES = (BYTES, JSON, IGNORE)
# A command goes to the program as a list; a shell would read it again.
SHELLS = frozenset({"sh", "bash", "zsh", "dash", "ksh", "fish", "cmd", "powershell", "pwsh"})
_NAME = re.compile(r"[a-z0-9][a-z0-9_-]*")
_CASE_KEYS = {"name", "command", "cwd", "stdin", "outputs"}
_OUTPUT_KEYS = {"kind", "path", "rule", "ignore"}


@dataclass(frozen=True)
class DifferentialOutput:
    """One thing a case compares. ``ignore`` holds the regular expressions of the lines the
    ``ignore`` rule drops before comparing the bytes."""

    kind: str
    rule: str = BYTES
    path: str = ""
    ignore: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"kind": self.kind, "rule": self.rule}
        if self.path:
            data["path"] = self.path
        if self.ignore:
            data["ignore"] = list(self.ignore)
        return data


DEFAULT_OUTPUTS = (DifferentialOutput(STDOUT), DifferentialOutput(EXIT_CODE))


@dataclass(frozen=True)
class DifferentialCase:
    """``cwd`` and ``stdin`` are repository-relative; empty ``cwd`` is the root, empty ``stdin``
    is no input. A difference no rule excuses is a difference."""

    name: str
    command: tuple[str, ...]
    outputs: tuple[DifferentialOutput, ...] = DEFAULT_OUTPUTS
    cwd: str = ""
    stdin: str = ""

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "name": self.name,
            "command": list(self.command),
            "outputs": [output.to_dict() for output in self.outputs],
        }
        if self.cwd:
            data["cwd"] = self.cwd
        if self.stdin:
            data["stdin"] = self.stdin
        return data


def merge_differential(
    layers: Sequence[Mapping[str, Any]], problems: list[str]
) -> tuple[DifferentialCase, ...]:
    """The cases of every configuration layer, in the order they were read. A name used twice is
    a problem, whichever file declared it. ``layers`` are the parsed layers' data."""
    found: dict[str, DifferentialCase] = {}
    for data in layers:
        for raw in data.get("differential", {}).get("cases", []):
            case = _case(raw)
            if case.name in found:
                problems.append(f"differential.cases: the case name {case.name!r} is used twice")
            found[case.name] = case
    return tuple(found.values())


def _case(raw: Mapping[str, Any]) -> DifferentialCase:
    outputs = tuple(
        DifferentialOutput(
            output["kind"],
            output.get("rule", BYTES),
            output.get("path", ""),
            tuple(output.get("ignore", ())),
        )
        for output in raw.get("outputs", ())
    )
    return DifferentialCase(
        raw["name"],
        tuple(raw["command"]),
        outputs or DEFAULT_OUTPUTS,
        raw.get("cwd", ""),
        raw.get("stdin", ""),
    )


def validate_differential(section: Any, bad: Any) -> None:
    if section is None:
        return
    if not isinstance(section, dict):
        bad("differential", "must be a table")
        return
    for key in sorted(set(section) - {"cases"}):
        bad(f"differential.{key}", "unknown key")
    cases = section.get("cases")
    if cases is None:
        return
    if not isinstance(cases, list) or not all(isinstance(item, dict) for item in cases):
        bad("differential.cases", "must be a list of tables")
        return
    for position, item in enumerate(cases):
        where = f"differential.cases[{position}]"
        for key in sorted(set(item) - _CASE_KEYS):
            bad(f"{where}.{key}", "unknown key")
        _validate_name(item.get("name"), where, bad)
        _validate_command(item.get("command"), where, bad)
        for key in ("cwd", "stdin"):
            if key in item:
                _validate_path(item[key], f"{where}.{key}", bad)
        _validate_outputs(item.get("outputs"), where, bad)


def _validate_name(name: Any, where: str, bad: Any) -> None:
    if not isinstance(name, str) or not _NAME.fullmatch(name):
        bad(f"{where}.name", "must be lower-case words, digits, '-' or '_', starting with one")


def _validate_command(command: Any, where: str, bad: Any) -> None:
    if not (
        isinstance(command, list)
        and command
        and all(isinstance(part, str) and part for part in command)
    ):
        bad(f"{where}.command", "must be a non-empty list of strings (no shell string)")
        return
    program = PurePath(command[0].replace("\\", "/")).name.lower().removesuffix(".exe")
    if program in SHELLS:
        bad(f"{where}.command", f"{program} is a shell; give the program and its arguments")


def _validate_path(value: Any, where: str, bad: Any) -> None:
    try:
        if not isinstance(value, str):
            raise ValueError("must be a string")
        check_relative_path(value)
    except ValueError:
        bad(where, "must be a path inside the repository, as a relative POSIX path")


def _validate_outputs(outputs: Any, where: str, bad: Any) -> None:
    if outputs is None:
        return
    if (
        not isinstance(outputs, list)
        or not outputs
        or not all(isinstance(o, dict) for o in outputs)
    ):
        bad(f"{where}.outputs", "must be a non-empty list of tables")
        return
    seen: set[tuple[str, str]] = set()
    for position, output in enumerate(outputs):
        here = f"{where}.outputs[{position}]"
        for key in sorted(set(output) - _OUTPUT_KEYS):
            bad(f"{here}.{key}", "unknown key")
        kind, rule = output.get("kind"), output.get("rule", BYTES)
        if kind not in KINDS:
            bad(f"{here}.kind", f"must be one of: {', '.join(KINDS)}")
            continue
        if rule not in RULES:
            bad(f"{here}.rule", f"must be one of: {', '.join(RULES)}")
        elif kind == EXIT_CODE and rule != BYTES:
            bad(f"{here}.rule", "the exit code is compared exactly")
        _validate_output_path(kind, output, here, bad)
        _validate_ignore(rule, output.get("ignore"), here, bad)
        key = (kind, str(output.get("path", "")))
        if key in seen:
            bad(here, "this output is listed twice")
        seen.add(key)


def _validate_output_path(kind: str, output: Mapping[str, Any], where: str, bad: Any) -> None:
    if kind == FILE:
        if "path" not in output:
            bad(f"{where}.path", "a file output needs the path of the file")
        else:
            _validate_path(output["path"], f"{where}.path", bad)
    elif "path" in output:
        bad(f"{where}.path", "only a file output has a path")


def _validate_ignore(rule: Any, patterns: Any, where: str, bad: Any) -> None:
    if rule != IGNORE:
        if patterns is not None:
            bad(f"{where}.ignore", "only the rule 'ignore' takes patterns")
        return
    if not (isinstance(patterns, list) and patterns and all(isinstance(p, str) for p in patterns)):
        bad(f"{where}.ignore", "the rule 'ignore' needs a non-empty list of regular expressions")
        return
    for pattern in patterns:
        try:
            compiled = re.compile(pattern)
        except re.error as error:
            bad(f"{where}.ignore", f"{pattern!r} is not a valid regular expression: {error}")
            continue
        if compiled.match(""):
            bad(f"{where}.ignore", f"{pattern!r} matches the empty string, so it drops every line")
