"""The user guide names every command-line argument and every key of execucao.toml and forja.toml.

The names come from the code (the parser, the pydantic models, the policy validators and the check
registry), never from the guide, so a new argument or key that nobody documented fails here.
"""

import argparse
import re
from pathlib import Path

import pytest

from forja.checks.specs import default_registry
from forja.cli.args import parser
from forja.cli.settings import Execucao, Interface, ModeloCli
from forja.core.policy.config import _CHECK_KEYS, ADAPTER_OPERATIONS, SECTION_KEYS
from forja.core.policy.differential import _CASE_KEYS, _OUTPUT_KEYS

GUIDE = Path(__file__).resolve().parents[2] / "docs" / "guia"
GUIDE_TEXT = "\n".join(path.read_text(encoding="utf-8") for path in sorted(GUIDE.rglob("*.md")))


def _named(name: str) -> bool:
    """The name appears as code: in backticks, as a TOML key, or inside a table header."""
    escaped = re.escape(name)
    pattern = rf"`{escaped}`|^\s*{escaped}\s*=|^\s*\[+[\w.\-\"]*\b{escaped}\b[\w.\-\"]*\]+"
    return re.search(pattern, GUIDE_TEXT, re.MULTILINE) is not None


def _parsers() -> list[argparse.ArgumentParser]:
    main = parser()
    found = [main]
    for action in main._actions:  # noqa: SLF001
        if isinstance(action, argparse._SubParsersAction):  # noqa: SLF001
            found += [item for name, item in action.choices.items() if name != "agente"]
    return found


def _long_options() -> set[str]:
    return {
        option
        for item in _parsers()
        for action in item._actions  # noqa: SLF001
        for option in action.option_strings
        if option.startswith("--") and option != "--help"
    }


def _commands() -> set[str]:
    main = parser()
    return {
        name
        for action in main._actions  # noqa: SLF001
        if isinstance(action, argparse._SubParsersAction)  # noqa: SLF001
        for name in action.choices
        if name != "agente"
    }


def _check_key_names() -> set[str]:
    registry = default_registry()
    names: set[str] = set()
    for spec in registry:
        names |= spec.thresholds | spec.commands | spec.limits
    return names


def test_the_guide_exists() -> None:
    assert GUIDE_TEXT


@pytest.mark.parametrize("option", sorted(_long_options()))
def test_every_argument_is_in_the_guide(option: str) -> None:
    assert option in GUIDE_TEXT, f"{option} is not in docs/guia"


@pytest.mark.parametrize("command", sorted(_commands()))
def test_every_command_is_in_the_guide(command: str) -> None:
    assert _named(command) or f"forja {command}" in GUIDE_TEXT, f"{command} is not in docs/guia"


@pytest.mark.parametrize(
    "key",
    sorted(set(Execucao.model_fields) | set(Interface.model_fields) | set(ModeloCli.model_fields)),
)
def test_every_execucao_key_is_in_the_guide(key: str) -> None:
    assert _named(key), f"execucao.toml: {key} is not in docs/guia"


@pytest.mark.parametrize(
    "key",
    sorted(
        set(SECTION_KEYS)
        | {key for keys in SECTION_KEYS.values() for key in keys}
        | _CHECK_KEYS
        | ADAPTER_OPERATIONS
        | _CASE_KEYS
        | _OUTPUT_KEYS
        | {"name", "paths"}
        | _check_key_names()
    ),
)
def test_every_forja_toml_key_is_in_the_guide(key: str) -> None:
    assert _named(key), f"forja.toml: {key} is not in docs/guia"


@pytest.mark.parametrize("check_id", sorted(spec.id for spec in default_registry()))
def test_every_check_is_in_the_guide(check_id: str) -> None:
    assert _named(check_id), f"check {check_id} is not in docs/guia"
