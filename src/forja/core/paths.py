import os
import sys
from collections.abc import Mapping
from pathlib import Path


def forja_home(
    *,
    environ: Mapping[str, str] | None = None,
    platform: str | None = None,
    home: Path | None = None,
) -> Path:
    """Where Forja keeps run data, outside the target repository so diffs stay clean.

    ``FORJA_HOME`` wins; otherwise ``%LOCALAPPDATA%\\forja`` on Windows and
    ``~/.local/share/forja`` elsewhere.
    """
    env = os.environ if environ is None else environ
    home = Path.home() if home is None else home
    platform = sys.platform if platform is None else platform
    if override := env.get("FORJA_HOME"):
        return Path(override)
    if platform == "win32":
        return Path(env.get("LOCALAPPDATA") or home / "AppData" / "Local") / "forja"
    return home / ".local" / "share" / "forja"


def locks_dir(repo_id: str, **kwargs: object) -> Path:
    """Where the locks of one repository live; ``repo_id`` comes from ``repository_id``."""
    return forja_home(**kwargs) / "locks" / repo_id  # type: ignore[arg-type]


def run_dir(run_id: str, **kwargs: object) -> Path:
    """Directory of one run: event log, artifacts and raw logs."""
    return forja_home(**kwargs) / "runs" / run_id  # type: ignore[arg-type]
