"""Acceptance: on three different repositories a run goes from the command to the delivery."""

import json
from pathlib import Path

import pytest

from tests.acceptance.samples import SAMPLES, Sample, build
from tests.cli.test_e2e import USAGE, Armed, Outcome, arm, forja, run

pytestmark = [pytest.mark.integration, pytest.mark.slow]


def go(
    sample: Sample,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> Outcome:
    repo = build(sample, tmp_path)
    declared = {
        "actions": [
            {
                "summary": "a lookup table instead of a chain",
                "reason": "the complexity was the number of branches",
                "files": [{"path": sample.target, "change": "modified"}],
            }
        ]
    }
    armed: Armed = arm(
        tmp_path,
        monkeypatch,
        {"writes": {sample.target: sample.after}, "saida": declared, "lines": [json.dumps(USAGE)]},
        repo,
    )
    code, talk = forja(armed, "--config", str(armed.answers), "refatorar")
    return Outcome(code, capsys.readouterr().out + talk.text, repo, armed.before)


@pytest.mark.parametrize("name", list(SAMPLES))
def test_the_command_ends_in_a_delivered_branch(
    name: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    sample = SAMPLES[name]

    result = go(sample, tmp_path, monkeypatch, capsys)

    assert result.code == 0, result.text
    assert sample.marker in result.delivered(sample.target)
    assert run("rev-parse", "HEAD", cwd=result.repo) == result.before
    assert run("status", "--porcelain", cwd=result.repo) == ""
    assert "Nenhuma tarefa foi integrada" not in result.text
