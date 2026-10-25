"""``forja revisao``: what of a run reached the main branch, read from git, changing nothing."""

import asyncio
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from forja.cli.args import parse
from forja.cli.main import amain
from forja.cli.prepare import Refused
from forja.cli.review import REVIEWS_DIR, principal, read_landed
from forja.core.artifacts.models import Producer
from forja.core.idempotency.git import Git
from forja.orchestrator.ports import PlannedTask
from tests.cli.test_main import Talk, git
from tests.orchestrator.fakes import ScriptedAgent, ScriptedMeasurer, ScriptedPlanner
from tests.orchestrator.harness import RUN, World, build_template

pytestmark = pytest.mark.integration

RUN_BRANCH = f"forja-run/{RUN}"
TASK = PlannedTask(
    "reduce the complexity of f",
    ("src/a.py",),
    8,
    400,
    stages=(Producer.IMPLEMENTER, Producer.DOCUMENTER),
)


def head(repo: Path) -> str:
    done = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True
    )
    return done.stdout.strip()


def refs(repo: Path) -> str:
    done = subprocess.run(
        ["git", "for-each-ref"], cwd=repo, check=True, capture_output=True, text=True
    )
    return done.stdout


def commit(repo: Path, subject: str, *trailers: str) -> None:
    (repo / "log.txt").write_text(f"{subject}\n{os.urandom(4).hex()}\n", encoding="utf-8")
    git(repo, "add", ".")
    args = ["commit", "-q", "-m", subject]
    for trailer in trailers:
        args += ["--trailer", trailer]
    git(repo, *args)


def reader(repo: Path, scratch: Path) -> Git:
    return Git(repo, executable=shutil.which("git") or "git", env={}, timeout=30, log_dir=scratch)


@pytest.fixture
def plain(tmp_path: Path) -> Path:
    path = tmp_path / "plain"
    path.mkdir()
    git(path, "init", "-q", "-b", "main")
    commit(path, "init")
    return path


# -- the arguments ------------------------------------------------------------------------------


def test_the_arguments_of_the_command_are_the_run_the_main_branch_and_the_comments() -> None:
    args = parse(["revisao", "r9", "--principal", "origin/main", "--fatos", "c.txt"])

    assert (args.command, args.run, args.main_ref, args.facts) == (
        "revisao",
        "r9",
        "origin/main",
        Path("c.txt"),
    )
    assert parse(["revisao"]).run == ""
    assert parse(["revisao"]).main_ref == ""


# -- reading the main branch --------------------------------------------------------------------


def test_only_what_the_main_branch_gained_after_the_base_is_read(
    plain: Path, tmp_path: Path
) -> None:
    commit(plain, "old", "Task-Id: t1", "Stage-Id: t1-s")
    base = head(plain)
    commit(plain, "new", "Task-Id: t1", "Stage-Id: t1-d")
    commit(plain, "merge", "Task-Id: t1")
    commit(plain, "other", "Task-Id: t2")
    commit(plain, "plain")

    landed = asyncio.run(read_landed(reader(plain, tmp_path), base, head(plain)))

    assert landed.stages == frozenset({"t1-d"})
    assert dict(landed.loose) == {"t1": 1, "t2": 1}


def test_a_commit_with_several_stage_ids_counts_each(plain: Path, tmp_path: Path) -> None:
    base = head(plain)
    commit(plain, "both", "Task-Id: t1", "Stage-Id: t1-s", "Stage-Id: t1-d")

    landed = asyncio.run(read_landed(reader(plain, tmp_path), base, head(plain)))

    assert landed.stages == frozenset({"t1-s", "t1-d"})
    assert dict(landed.loose) == {}


def test_a_main_branch_with_nothing_new_has_nothing_landed(plain: Path, tmp_path: Path) -> None:
    landed = asyncio.run(read_landed(reader(plain, tmp_path), head(plain), head(plain)))

    assert (landed.stages, dict(landed.loose)) == (frozenset(), {})


@pytest.mark.parametrize("base", ["f" * 40, "not-a-commit", "--all"])
def test_a_base_commit_this_repository_lacks_or_that_is_not_a_commit_is_refused(
    plain: Path, tmp_path: Path, base: str
) -> None:
    with pytest.raises(Refused) as refused:
        asyncio.run(read_landed(reader(plain, tmp_path), base, head(plain)))

    assert refused.value.code == 2
    assert base[:12] in refused.value.message


def test_the_main_branch_is_the_one_named_and_what_it_points_to(
    plain: Path, tmp_path: Path
) -> None:
    git(plain, "update-ref", "refs/remotes/origin/main", "HEAD")
    git(plain, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main")
    where = reader(plain, tmp_path)

    named = asyncio.run(principal(where, "main"))
    pointed = asyncio.run(principal(where, ""))

    assert named == ("main", head(plain))
    assert pointed == ("origin/main", head(plain))


# -- the command, after a real run --------------------------------------------------------------


@pytest.fixture(scope="session")
def template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("template") / "repo"
    build_template(path)
    return path


@pytest.fixture
def delivered(
    tmp_path: Path, template: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[World, dict[str, str]]:
    """A real run that delivered, its log in the Forja home, the shell in its repository."""
    world = World.create(tmp_path / "world", template)
    world.run(
        measurer=ScriptedMeasurer(),
        agent=ScriptedAgent(edits=[{"src/a.py": "def f():\n    return 1\n"}]),
        agents={Producer.DOCUMENTER: ScriptedAgent(edits=[{"README.md": "# a\n"}])},
        planner=ScriptedPlanner((TASK,)),
    )
    home = tmp_path / "forja-home"
    (home / "runs" / RUN).mkdir(parents=True)
    shutil.copy(world.run_dir / "events.jsonl", home / "runs" / RUN / "events.jsonl")
    monkeypatch.setenv("FORJA_HOME", str(home))
    monkeypatch.chdir(world.repo.path)
    return world, {**os.environ, "FORJA_HOME": str(home)}


def collect(*argv: str, environ: dict[str, str]) -> tuple[int, Talk]:
    talk = Talk()
    code = asyncio.run(amain(parse(["revisao", *argv]), talk, environ))
    return code, talk


def report(environ: dict[str, str]) -> str:
    return (Path(environ["FORJA_HOME"]) / REVIEWS_DIR / f"{RUN}.md").read_text(encoding="utf-8")


def stage_commit(world: World, stage: str) -> str:
    return world.repo.sh("log", RUN_BRANCH, "--format=%H", f"--grep=^Stage-Id: {stage}$")


def test_before_the_person_takes_anything_nothing_has_arrived(
    delivered: tuple[World, dict[str, str]],
) -> None:
    _, environ = delivered

    code, talk = collect("--principal", "main", environ=environ)

    text = report(environ)
    assert code == 0
    assert str(Path(environ["FORJA_HOME"]) / REVIEWS_DIR / f"{RUN}.md") in talk.text
    assert "- `t1` (reduce the complexity of f): não chegou." in text
    assert f"- Estilo (`Stage-Id: normalize-{RUN}`): não está na principal" in text


def test_a_merge_of_the_run_branch_brings_every_stage_and_the_style_commit(
    delivered: tuple[World, dict[str, str]],
) -> None:
    world, environ = delivered
    world.repo.sh("merge", "--no-ff", "-m", "take the run", RUN_BRANCH)

    collect("--principal", "main", environ=environ)

    text = report(environ)
    assert "- `t1` (reduce the complexity of f): chegou inteira." in text
    assert "  - `Stage-Id: t1-s` (implementador): chegou." in text
    assert "  - `Stage-Id: t1-d` (documentador): chegou." in text
    assert f"- Estilo (`Stage-Id: normalize-{RUN}`): chegou." in text
    assert "e sem `Stage-Id` na principal" in text


def test_a_fast_forward_brings_the_stages_without_the_merge_of_the_task(
    delivered: tuple[World, dict[str, str]],
) -> None:
    world, environ = delivered
    world.repo.sh("merge", "--ff-only", RUN_BRANCH)

    collect("--principal", "main", environ=environ)

    assert "chegou inteira" in report(environ)


def test_one_commit_taken_alone_is_a_task_that_arrived_in_part(
    delivered: tuple[World, dict[str, str]],
) -> None:
    world, environ = delivered
    world.repo.sh("cherry-pick", stage_commit(world, "t1-s"))

    collect("--principal", "main", environ=environ)

    text = report(environ)
    assert "chegou em parte (1 de 2 etapas com commit)" in text
    assert "  - `Stage-Id: t1-s` (implementador): chegou." in text
    assert "  - `Stage-Id: t1-d` (documentador): não chegou." in text


def test_a_squash_erases_the_trailers_and_the_report_says_it_cannot_see(
    delivered: tuple[World, dict[str, str]],
) -> None:
    world, environ = delivered
    world.repo.sh("merge", "--squash", RUN_BRANCH)
    world.repo.sh("commit", "-m", "the whole run in one commit")

    collect("--principal", "main", environ=environ)

    text = report(environ)
    assert "- `t1` (reduce the complexity of f): não chegou." in text
    assert "Squash ou rebase que reescreve as mensagens apaga" in text


def test_the_repository_is_left_as_it_was(delivered: tuple[World, dict[str, str]]) -> None:
    world, environ = delivered
    world.repo.sh("merge", "--no-ff", "-m", "take the run", RUN_BRANCH)
    repo = world.repo.path
    before = (refs(repo), head(repo), sorted(p.name for p in repo.iterdir()))

    collect("--principal", "main", environ=environ)

    assert (refs(repo), head(repo), sorted(p.name for p in repo.iterdir())) == before


def test_without_a_name_the_main_branch_is_the_one_origin_points_to(
    delivered: tuple[World, dict[str, str]],
) -> None:
    world, environ = delivered
    world.repo.sh("merge", "--ff-only", RUN_BRANCH)
    world.repo.sh("update-ref", "refs/remotes/origin/main", "HEAD")
    world.repo.sh("symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main")

    code, _ = collect(environ=environ)

    assert code == 0
    assert "Principal lida: `origin/main`" in report(environ)


def test_without_origin_the_command_asks_which_branch_is_the_main_one(
    delivered: tuple[World, dict[str, str]],
) -> None:
    _, environ = delivered

    code, talk = collect(environ=environ)

    assert code == 2
    assert "--principal origin/main" in talk.text


@pytest.mark.parametrize("name", ["origin/nope", "-x"])
def test_a_main_branch_that_does_not_exist_or_looks_like_an_option_is_refused(
    delivered: tuple[World, dict[str, str]], name: str
) -> None:
    _, environ = delivered

    code, talk = collect(f"--principal={name}", environ=environ)

    assert code == 2
    assert name in talk.text
    assert not (Path(environ["FORJA_HOME"]) / REVIEWS_DIR).exists()


def test_a_run_is_picked_by_id_and_an_unknown_id_is_not_found(
    delivered: tuple[World, dict[str, str]],
) -> None:
    _, environ = delivered

    found, _ = collect(RUN, "--principal", "main", environ=environ)
    code, talk = collect("nope", "--principal", "main", environ=environ)

    assert found == 0
    assert code == 2
    assert "A execução nope não é deste repositório ou não existe." in talk.text


def test_without_any_run_there_is_nothing_to_collect(
    plain: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(plain)
    environ = {**os.environ, "FORJA_HOME": str(tmp_path / "empty-home")}

    code, talk = collect("--principal", "main", environ=environ)

    assert code == 2
    assert "Nenhuma execução da Forja neste repositório." in talk.text


def test_outside_a_repository_the_command_says_where_to_run_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.chdir(empty)

    code, talk = collect(environ={**os.environ, "FORJA_HOME": str(tmp_path / "home")})

    assert code == 2
    assert "dentro do repositório da execução" in talk.text


def test_the_comments_file_feeds_the_report_and_a_bad_one_stops_the_command(
    delivered: tuple[World, dict[str, str]], tmp_path: Path
) -> None:
    _, environ = delivered
    good = tmp_path / "comentarios.txt"
    good.write_text("c1 | Ana | 2026-10-25 | o teste cobre o caso\n", encoding="utf-8")
    bad = tmp_path / "ruim.txt"
    bad.write_text("isto não é um fato\n", encoding="utf-8")

    done, _ = collect("--principal", "main", "--fatos", str(good), environ=environ)
    code, talk = collect("--principal", "main", "--fatos", str(bad), environ=environ)
    missing, said = collect("--principal", "main", "--fatos", str(tmp_path / "x"), environ=environ)

    assert done == 0
    assert "- `c1` (Ana, 2026-10-25): o teste cobre o caso" in report(environ)
    assert code == 2
    assert "não servem" in talk.text
    assert missing == 2
    assert "Não consegui ler os comentários" in said.text
