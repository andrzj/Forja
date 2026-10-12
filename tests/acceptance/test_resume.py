"""Acceptance: a run cut short during the agent's call resumes and delivers the same work."""

import asyncio
import json
import os
from pathlib import Path

import pytest

from forja.cli import main as door
from forja.cli.args import parse
from forja.cli.resume import discard, find_unfinished, read_run
from tests.cli.test_e2e import AFTER, DECLARED, USAGE, Armed, arm, forja, run
from tests.cli.test_main import Talk

pytestmark = [pytest.mark.integration, pytest.mark.slow]


def script(pause: float) -> dict[str, object]:
    return {
        "writes": {"src/pkg/mod.py": AFTER},
        "saida": DECLARED,
        "lines": [json.dumps(USAGE)],
        "sleep": pause,
    }


def cut_while_the_agent_works(armed: Armed, tmp_path: Path) -> int:
    started = tmp_path / "record.json"

    async def go() -> int:
        task = asyncio.create_task(
            door.amain(
                parse(["--config", str(armed.answers), "refatorar"]), Talk(), dict(os.environ)
            )
        )
        for _ in range(600):
            if started.exists():
                break
            await asyncio.sleep(0.1)
        assert started.exists(), "the agent never started"
        await asyncio.sleep(0.5)
        task.cancel()  # what a signal does to the process
        return await task

    return asyncio.run(go())


def test_a_run_cut_during_the_agents_call_resumes_and_delivers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    armed = arm(tmp_path, monkeypatch, script(pause=60))

    first = cut_while_the_agent_works(armed, tmp_path)

    assert first == 130
    assert run("branch", "--list", "forja-run/*", cwd=armed.repo) != ""
    armed.script.write_text(
        json.dumps({"record": str(tmp_path / "record2.json"), **script(pause=0)}),
        encoding="utf-8",
    )

    code, talk = forja(armed, "refatorar", talk=Talk(interactive=True))

    assert code == 0, talk.text
    assert "incompleta" in talk.text
    branches = [
        b.strip(" *+") for b in run("branch", "--list", "forja-run/*", cwd=armed.repo).splitlines()
    ]
    assert len(branches) == 1
    assert run("show", f"{branches[0]}:src/pkg/mod.py", cwd=armed.repo) == AFTER.strip()
    assert run("rev-parse", "HEAD", cwd=armed.repo) == armed.before
    assert run("status", "--porcelain", cwd=armed.repo) == ""


def test_a_discarded_run_stays_on_disk_and_a_new_one_starts_clean(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    armed = arm(tmp_path, monkeypatch, script(pause=60))
    cut_while_the_agent_works(armed, tmp_path)
    home = Path(os.environ["FORJA_HOME"])
    [old] = find_unfinished(home, armed.repo)
    discard(old.directory)
    armed.script.write_text(
        json.dumps({"record": str(tmp_path / "record2.json"), **script(pause=0)}),
        encoding="utf-8",
    )

    code, talk = forja(armed, "--config", str(armed.answers), "refatorar")

    assert code == 0, talk.text
    assert find_unfinished(home, armed.repo) == []
    assert (old.directory / "events.jsonl").exists()
    assert read_run(old.directory) == (str(armed.repo), "discarded", "discarded_by_user")
    branches = run("branch", "--list", "forja-run/*", cwd=armed.repo).splitlines()
    assert len(branches) == 2, branches  # the old branch is the person's to remove
    assert run("rev-parse", "HEAD", cwd=armed.repo) == armed.before


def test_a_run_does_not_resume_under_a_policy_other_than_the_one_it_was_confirmed_with(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    armed = arm(tmp_path, monkeypatch, script(pause=60))
    cut_while_the_agent_works(armed, tmp_path)
    (armed.repo / "forja.toml").write_text(
        "[checks.secrets]" + chr(10) + 'mode = "observation"' + chr(10), encoding="utf-8"
    )

    code, talk = forja(armed, "refatorar", talk=Talk(interactive=True))

    assert code == 2, talk.text
    assert "forja.toml mudou" in talk.text
    assert find_unfinished(Path(os.environ["FORJA_HOME"]), armed.repo) != []
