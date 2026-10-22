"""The Semgrep rules are the user's: where they come from, what is refused, what is told."""

import asyncio
from pathlib import Path
from typing import Any

import pytest

from forja.checks.changes import Change, ChangeKind, Changes
from forja.checks.scope import ScopeCheck
from forja.cli.args import Arguments, parse
from forja.cli.doctor import _has_rules
from forja.cli.prepare import NO_RULES, Refused, semgrep_rules
from forja.cli.semgrep_rules import RulesError, explicit_rules, export_rules, rules_in_commit
from forja.cli.settings import Execucao, dumps, load_execucao
from forja.core.adapters import FileClass
from forja.core.artifacts.models import Producer
from forja.core.gates import GateInput, Rejected
from forja.languages.python import PythonAdapter
from forja.orchestrator.config import RunConfig
from forja.orchestrator.ports import TaskInfo
from forja.orchestrator.summary import Facts, render_summary
from tests.core.idempotency.conftest import Repo, repo  # noqa: F401 - re-exported as a fixture


def run(coroutine: Any) -> Any:
    return asyncio.run(coroutine)


@pytest.mark.parametrize(
    "reference",
    ["auto", "p/python", "r/python.lang", "s/abc", "semgrep.dev/p/ci", "https://x.dev/r.yml"],
)
def test_a_registry_reference_is_refused(reference: str) -> None:
    with pytest.raises(RulesError, match="registro do Semgrep"):
        explicit_rules(reference)


def test_rules_that_do_not_exist_are_refused(tmp_path: Path) -> None:
    with pytest.raises(RulesError, match="Não encontrei"):
        explicit_rules(str(tmp_path / "nope.yml"))


def test_a_local_file_or_directory_is_taken_as_an_absolute_path(tmp_path: Path) -> None:
    (tmp_path / "r.yml").write_text("rules: []", encoding="utf-8")
    (tmp_path / "dir").mkdir()

    assert explicit_rules(str(tmp_path / "r.yml")) == (tmp_path / "r.yml").resolve()
    assert explicit_rules(str(tmp_path / "dir")) == (tmp_path / "dir").resolve()


def test_the_rules_of_a_commit_are_found_and_a_commit_without_them_has_none(
    repo: Repo,  # noqa: F811
) -> None:
    assert run(rules_in_commit(repo.git, "HEAD")) == ()
    (repo.path / ".semgrep").mkdir()
    (repo.path / ".semgrep" / "a.yml").write_text("a", encoding="utf-8")
    repo.commit(".semgrep.yml")
    repo.sh("add", ".semgrep")
    repo.sh("commit", "-m", "rules")

    assert run(rules_in_commit(repo.git, "HEAD")) == (".semgrep.yml", ".semgrep/a.yml")


def test_the_copy_is_made_from_the_commit_and_not_from_the_working_tree(
    repo: Repo,  # noqa: F811
    tmp_path: Path,
) -> None:
    commit = repo.commit(".semgrep.yml")
    (repo.path / ".semgrep.yml").write_text("edited by the agent", encoding="utf-8")
    target = tmp_path / "copy"

    found = run(export_rules(repo.git, commit, "", target))

    assert found == target
    assert (target / "semgrep.yml").read_text(encoding="utf-8").strip() == ".semgrep.yml"
    assert not (target / ".semgrep.yml").exists()


def test_a_directory_of_rules_keeps_its_layout(repo: Repo, tmp_path: Path) -> None:  # noqa: F811
    (repo.path / ".semgrep" / "sub").mkdir(parents=True)
    (repo.path / ".semgrep" / "sub" / "r.yml").write_text("r", encoding="utf-8")
    repo.sh("add", ".semgrep")
    repo.sh("commit", "-m", "rules")
    target = tmp_path / "copy"

    run(export_rules(repo.git, repo.sh("rev-parse", "HEAD"), "", target))

    assert (target / "semgrep" / "sub" / "r.yml").read_text(encoding="utf-8").strip() == "r"


def test_without_rules_there_is_no_copy(repo: Repo, tmp_path: Path) -> None:  # noqa: F811
    target = tmp_path / "copy"
    target.mkdir()
    (target / "old.yml").write_text("old", encoding="utf-8")

    assert run(export_rules(repo.git, "HEAD", "", target)) is None
    assert not target.exists()


def test_named_rules_are_copied_whatever_the_repository_has(
    repo: Repo,  # noqa: F811
    tmp_path: Path,
) -> None:
    commit = repo.commit(".semgrep.yml")
    mine = tmp_path / "mine"
    mine.mkdir()
    (mine / "r.yml").write_text("mine", encoding="utf-8")
    target = tmp_path / "copy"

    found = run(export_rules(repo.git, commit, str(mine), target))
    single = run(export_rules(repo.git, commit, str(mine / "r.yml"), target))

    assert single == target / "r.yml" and single.read_text(encoding="utf-8") == "mine"
    assert found == target / "mine"  # the second call started from an empty target
    assert not (target / "mine").exists()


def test_a_named_registry_reference_stops_the_copy(tmp_path: Path, repo: Repo) -> None:  # noqa: F811
    with pytest.raises(RulesError):
        run(export_rules(repo.git, "HEAD", "p/ci", tmp_path / "copy"))


def args_with(*argv: str) -> Arguments:
    return parse(["refatorar", *argv])


def test_the_summary_line_says_where_the_rules_come_from_or_that_there_are_none(
    repo: Repo,  # noqa: F811
    tmp_path: Path,
) -> None:
    environ: dict[str, str] = dict(repo.env)
    head = repo.sh("rev-parse", "HEAD")

    assert run(semgrep_rules(args_with(), None, repo.path, head, environ)) == ("", NO_RULES)
    assert "SAST NÃO EXECUTADO" in NO_RULES

    commit = repo.commit(".semgrep.yml")
    assert run(semgrep_rules(args_with(), None, repo.path, commit, environ)) == (
        "",
        "SAST: Semgrep com as regras do repositório (.semgrep.yml)",
    )

    mine = tmp_path / "r.yml"
    mine.write_text("x", encoding="utf-8")
    path, line = run(
        semgrep_rules(args_with("--semgrep-config", str(mine)), None, repo.path, commit, environ)
    )
    assert path == str(mine.resolve()) and str(mine.resolve()) in line

    saved = Execucao(semgrep_config=str(mine))
    assert run(semgrep_rules(args_with(), saved, repo.path, commit, environ))[0] == str(
        mine.resolve()
    )


def test_a_registry_reference_stops_the_preparation(repo: Repo) -> None:  # noqa: F811
    with pytest.raises(Refused) as stop:
        run(semgrep_rules(args_with("--semgrep-config", "p/ci"), None, repo.path, "HEAD", {}))

    assert stop.value.code == 2 and "registro do Semgrep" in stop.value.message


def test_the_option_is_read_as_typed_in_both_forms() -> None:
    assert parse(["--semgrep-config", "p/ci"]).semgrep_config == "p/ci"
    assert parse(["refatorar", "--semgrep-config", "p/ci"]).semgrep_config == "p/ci"
    assert parse([]).semgrep_config == ""


def test_the_rules_the_person_named_are_kept_in_execucao_toml(tmp_path: Path) -> None:
    path = tmp_path / "execucao.toml"
    path.write_text(
        dumps(Execucao(semgrep_config="C:\\rules\\r.yml").model_dump()), encoding="utf-8"
    )

    assert load_execucao(path).semgrep_config == "C:\\rules\\r.yml"
    assert Execucao().semgrep_config == ""


def test_the_doctor_wants_semgrep_only_where_there_are_rules(tmp_path: Path) -> None:
    assert not _has_rules(tmp_path)
    (tmp_path / ".semgrep.yml").write_text("x", encoding="utf-8")
    assert _has_rules(tmp_path)
    (tmp_path / ".semgrep.yml").unlink()
    (tmp_path / ".semgrep").mkdir()
    assert _has_rules(tmp_path)


def test_the_delivery_summary_carries_the_notices(tmp_path: Path) -> None:
    config = RunConfig.model_validate(
        {
            "repo": "r",
            "base_commit": "c" * 40,
            "objective": "refactor",
            "implementer": {"name": "claude-code", "path": "p", "version": "1"},
            "forja_version": "0",
            "policy_version": "0",
        }
    )
    from forja.core.events import EventLog  # noqa: PLC0415
    from tests.checks.support import RUN  # noqa: PLC0415
    from tests.core.events.support import FakeClock  # noqa: PLC0415

    log = EventLog.open(tmp_path / "e.jsonl", RUN, clock=FakeClock())
    text = render_summary(log.state, Facts(), config, "b", Path("x"), ("SAST não executado: x",))

    assert "- **SAST não executado: x**" in text
    assert "SAST" not in render_summary(log.state, Facts(), config, "b", Path("x"))


def test_changing_the_rules_file_in_an_attempt_is_a_scope_violation() -> None:
    adapter = PythonAdapter()

    def classify(path: str) -> FileClass:
        return adapter.classify(path) or FileClass.OTHER

    for role in (Producer.IMPLEMENTER, Producer.TEST_AUTHOR):
        task = TaskInfo("t1", "t1-s", "intent", ("",), 8, 400, role=role)
        for path in (".semgrep.yml", ".semgrep/r.yml"):
            changes = Changes((Change(ChangeKind.MODIFIED, path),), 1, ())
            data = GateInput(Path("."), "c" * 40, "t1", "t1-s", "t1-a1")

            result = asyncio.run(ScopeCheck(changes, task, classify).evaluate(data))

            assert isinstance(result, Rejected), (role, path)


@pytest.mark.parametrize(
    ("name", "allowed"),
    [
        (".semgrep.yml", True),
        (".semgrep/a/b.yml", True),
        (".semgrep/..\\..\\x.yml", False),
        (".semgrep/../x.yml", False),
        (".semgrep//x.yml", False),
        (".semgrep/c:x.yml", False),
        ("/abs.yml", False),
    ],
)
def test_a_name_that_could_leave_the_copy_is_refused(name: str, allowed: bool) -> None:
    from forja.cli.semgrep_rules import _inside  # noqa: PLC0415

    assert _inside(name) is allowed
