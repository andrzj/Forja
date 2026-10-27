"""The input files of the differential cases, copied out of the worktree.

The implementer owns the worktree, so an input that stayed in it could be edited to hide a
difference. The copy is made from the base, once, and every run reads from it.
"""

import shutil
from collections.abc import Iterable
from pathlib import Path

from forja.checks.readme_gate import inside
from forja.core.policy.differential import DifferentialCase


class MissingInput(Exception):
    """A case names an input that is not a plain file inside the worktree."""

    def __init__(self, case: str, path: str) -> None:
        self.case = case
        self.path = path
        super().__init__(
            f"differential case {case}: the input {path} is not a file in the repository"
        )


def freeze_inputs(
    cases: Iterable[DifferentialCase], worktree: Path, destination: Path
) -> dict[str, Path]:
    """Copy each case's ``stdin`` to ``destination``; the copies by case name.

    Raises ``MissingInput`` for a path that is absent, outside the worktree, a directory or
    reached through a link.
    """
    frozen: dict[str, Path] = {}
    for case in cases:
        if not case.stdin:
            continue
        source = inside(worktree, case.stdin)
        if source is None or not source.is_file():
            raise MissingInput(case.name, case.stdin)
        destination.mkdir(parents=True, exist_ok=True)
        copy = destination / f"{case.name}.stdin"
        shutil.copyfile(source, copy)
        frozen[case.name] = copy
    return frozen
