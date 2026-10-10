import subprocess
from pathlib import Path

from forja.core.isolation import filter_environment, git_blocking_environment, looks_secret
from tests.core.idempotency.conftest import Repo, repo  # noqa: F401

HOST = {
    "Path": "C:/bin",
    "HOME": "/home/me",
    "LANG": "en_US.UTF-8",
    "LC_ALL": "C",
    "AWS_SECRET_ACCESS_KEY": "aws-secret-value",
    "GITHUB_TOKEN": "gh-token-value",
    "EDITOR": "vim",
    "ANTHROPIC_API_KEY": "cli-key-value",
    "ANTHROPIC_BASE_URL": "https://gateway.example",
}


def test_only_the_generic_allow_list_passes_and_the_hosts_spelling_is_kept() -> None:
    result = filter_environment(HOST)

    assert result.values == {
        "Path": "C:/bin",
        "HOME": "/home/me",
        "LANG": "en_US.UTF-8",
        "LC_ALL": "C",
    }
    assert result.withheld == ()


def test_the_variables_an_adapter_declares_pass_even_if_they_look_secret() -> None:
    result = filter_environment(HOST, adapter_allow=["ANTHROPIC_API_KEY", "anthropic_base_url"])

    assert result.values["ANTHROPIC_API_KEY"] == "cli-key-value"
    assert result.values["ANTHROPIC_BASE_URL"] == "https://gateway.example"
    assert "GITHUB_TOKEN" not in result.values and "AWS_SECRET_ACCESS_KEY" not in result.values


def test_a_secret_looking_name_in_the_base_list_is_held_back_and_reported_by_name_only() -> None:
    result = filter_environment(HOST, base_allow=["PATH", "GITHUB_TOKEN"])

    assert "GITHUB_TOKEN" not in result.values
    assert result.withheld == ("GITHUB_TOKEN",)
    assert "gh-token-value" not in repr(result.withheld)


def test_values_set_by_forja_are_added_last_and_win() -> None:
    result = filter_environment(HOST, extra={"HOME": "/tmp/agent", "GIT_DIR": "/nowhere"})

    assert result.values["HOME"] == "/tmp/agent"
    assert result.values["GIT_DIR"] == "/nowhere"


def test_secret_looking_names() -> None:
    for name in (
        "API_KEY",
        "github_token",
        "DB_PASSWORD",
        "CLIENT_SECRET",
        "AWS_CREDENTIALS",
        "PASSWD",
    ):
        assert looks_secret(name)
    for name in ("PATH", "HOME", "LANG", "EDITOR", "TERM"):
        assert not looks_secret(name)


def test_the_result_does_not_depend_on_the_host_being_mutated() -> None:
    host = dict(HOST)
    filter_environment(host)

    assert host == HOST


# -- git is blocked by construction in the agent's copy ---------------------------------------


def _git_status(env: dict[str, str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "status"], cwd=cwd, env=env, capture_output=True, text=True, check=False
    )


def test_git_fails_inside_a_copy_that_sits_under_a_repository(repo: Repo) -> None:  # noqa: F811
    copy = repo.path / "copy"
    copy.mkdir()
    (copy / "file.txt").write_text("x")

    assert _git_status(repo.env, copy).returncode == 0  # the repository above is found
    blocked = {**repo.env, **git_blocking_environment(copy)}

    result = _git_status(blocked, copy)
    assert result.returncode != 0
    assert "not a git repository" in result.stderr


def test_the_ceiling_alone_already_stops_the_search_upward(repo: Repo) -> None:  # noqa: F811
    copy = repo.path / "copy"
    copy.mkdir()
    only_ceiling = {
        **repo.env,
        "GIT_CEILING_DIRECTORIES": git_blocking_environment(copy)["GIT_CEILING_DIRECTORIES"],
    }

    assert _git_status(only_ceiling, copy).returncode != 0


def test_the_blocking_variables_point_where_they_should(tmp_path: Path) -> None:
    copy = tmp_path / "attempt" / "copy"

    blocked = git_blocking_environment(copy)

    assert blocked["GIT_CEILING_DIRECTORIES"] == str(copy.parent)
    assert not Path(blocked["GIT_DIR"]).exists()
