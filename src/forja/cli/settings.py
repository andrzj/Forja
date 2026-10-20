"""What a run is asked to do and how it should look: ``execucao.toml`` and the user's profile.

Everything the preparation asks is written to ``execucao.toml``, and ``forja --config`` reads it
back without asking anything, for CI. The user's own preferences (where the CLIs are, the theme)
live in their profile, never in the repository.
"""

import os
import sys
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

DEFAULT_TOKENS = 2_000_000
Mode = Literal["auto", "completa", "linha", "texto"]


class SettingsError(Exception):
    """A settings file that cannot be used; the message says what to fix."""


class Interface(BaseModel):
    model_config = ConfigDict(extra="forbid")

    modo: Mode = "auto"
    tema: str = ""  # empty: follow the background of the terminal
    ascii: bool = False
    redimensionar: bool = True


class Execucao(BaseModel):
    """``execucao.toml``: the answers of the preparation."""

    model_config = ConfigDict(extra="forbid")

    objetivo: Literal["refatorar", "corrigir"] = "refatorar"
    descricao: str = ""
    arquivo: str = ""
    criterios: str = ""  # corrigir: the criteria file (CriteriaBody as JSON)
    cli: str = ""
    executavel: str = ""
    cli_testes: str = ""  # corrigir: the CLI of the test author; empty is the implementer's
    executavel_testes: str = ""
    escopo: list[str] = Field(default_factory=list)
    tokens: int = Field(default=DEFAULT_TOKENS, ge=1)
    agente_roda_testes: bool = True
    tarefas: int = Field(default=5, ge=1)  # how many of the worst functions one run takes on
    base: str = ""
    interface: Interface = Field(default_factory=Interface)


class Perfil(BaseModel):
    """``config.toml`` of the user: what is theirs and not the repository's."""

    model_config = ConfigDict(extra="forbid")

    cli: str = ""
    executaveis: dict[str, str] = Field(default_factory=dict)
    interface: Interface = Field(default_factory=Interface)


def profile_dir(environ: Mapping[str, str] | None = None, platform: str | None = None) -> Path:
    env = os.environ if environ is None else environ
    platform = sys.platform if platform is None else platform
    if override := env.get("FORJA_CONFIG_HOME"):
        return Path(override)
    if platform == "win32":
        return Path(env.get("APPDATA") or Path.home() / "AppData" / "Roaming") / "forja"
    base = env.get("XDG_CONFIG_HOME")
    return (Path(base) if base else Path.home() / ".config") / "forja"


def _read(path: Path) -> dict[str, object]:
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise SettingsError(f"cannot read {path}: {error.strerror}") from None
    except tomllib.TOMLDecodeError as error:
        raise SettingsError(f"{path} is not valid TOML: {error}") from None


def _explain(path: Path, error: ValidationError) -> SettingsError:
    problems = "; ".join(
        f"{'.'.join(str(part) for part in item['loc'])}: {item['msg']}" for item in error.errors()
    )
    return SettingsError(f"{path}: {problems}")


def load_execucao(path: Path) -> Execucao:
    data = _read(path)
    try:
        return Execucao.model_validate(data)
    except ValidationError as error:
        raise _explain(path, error) from None


def load_perfil(directory: Path) -> Perfil:
    path = directory / "config.toml"
    if not path.exists():
        return Perfil()
    try:
        return Perfil.model_validate(_read(path))
    except ValidationError as error:
        raise _explain(path, error) from None


def _value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, list):
        return "[" + ", ".join(_value(item) for item in value) + "]"
    text = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{text}"'


def dumps(data: Mapping[str, object]) -> str:
    """TOML for the flat values and one level of tables these files hold."""
    lines = [
        f"{key} = {_value(value)}" for key, value in data.items() if not isinstance(value, dict)
    ]
    for key, value in data.items():
        if isinstance(value, dict):
            lines += ["", f"[{key}]"]
            lines += [f"{name} = {_value(item)}" for name, item in value.items()]
    return "\n".join(lines) + "\n"


def save_execucao(path: Path, config: Execucao) -> None:
    path.write_text(dumps(config.model_dump()), encoding="utf-8", newline="\n")


def save_perfil(directory: Path, profile: Perfil) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "config.toml"
    path.write_text(dumps(profile.model_dump()), encoding="utf-8", newline="\n")
    return path
