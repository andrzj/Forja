"""The scanner step against the real gitleaks, when it is installed (it is skipped otherwise).

Written from gitleaks' documented interface (``stdin``, ``--exit-code``, ``--report-path``), without
the binary at hand: the first machine that has it is the first to run this.
"""

import shutil
from pathlib import Path

import pytest

from forja.core.gates import Approved, Rejected
from tests.checks.support import Scene, judge_with
from tests.core.idempotency.conftest import Repo

pytestmark = [
    pytest.mark.tools,
    pytest.mark.skipif(shutil.which("gitleaks") is None, reason="gitleaks is not installed"),
]

KEY = "AKIAZ7K3Q9X2M4V8B1NC"  # shaped like an AWS access key id, and not a real one


def test_a_key_in_the_added_lines_is_found_and_a_clean_change_is_not(
    repo: Repo, tmp_path: Path
) -> None:
    scene = Scene(repo, tmp_path / "scene", gitleaks=("gitleaks",))
    scene.write("src/sample/mod.py", "X = 1\n")
    clean = judge_with(scene, "secrets")

    scene.write("src/sample/mod.py", f'AWS_ACCESS_KEY_ID = "{KEY}"\n')
    leaked = judge_with(scene, "secrets")

    assert clean == Approved()
    assert isinstance(leaked, Rejected)
    assert KEY not in "".join(f.describe() for f in leaked.findings)
