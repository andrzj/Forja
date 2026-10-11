"""The agent's few commands: fixed, narrow, and unable to turn into anything else."""

from pathlib import Path

import pytest

from forja.cli.facade import PYTHON_VARIABLE, Refused, command_for, run_facade, safe_paths, tail


def test_paths_inside_the_project_are_accepted(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("x = 1\n", encoding="utf-8")
    assert safe_paths(tmp_path, ["src", "src/a.py"]) == ["src", "src/a.py"]


@pytest.mark.parametrize(
    "bad", ["--collect-only", "-x", "../outside", "src/../../x", "", "/etc/passwd", "C:\\Windows"]
)
def test_options_and_ways_out_are_refused(tmp_path: Path, bad: str) -> None:
    with pytest.raises(Refused):
        safe_paths(tmp_path, [bad])


def test_a_path_that_does_not_exist_is_refused(tmp_path: Path) -> None:
    with pytest.raises(Refused, match="não encontrado"):
        safe_paths(tmp_path, ["nada.py"])


def test_a_link_pointing_out_of_the_project_is_refused(tmp_path: Path) -> None:
    outside = tmp_path / "fora"
    outside.mkdir()
    project = tmp_path / "proj"
    project.mkdir()
    try:
        (project / "ponte").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("no permission to create links here")
    with pytest.raises(Refused):
        safe_paths(project, ["ponte"])


def test_the_tests_run_with_the_python_of_the_project() -> None:
    command = command_for("testar", ["tests"], {PYTHON_VARIABLE: "/p/python"})
    assert command[:3] == ["/p/python", "-m", "pytest"]
    assert command[-1] == "tests"


def test_lint_and_measure_default_to_the_whole_project() -> None:
    assert command_for("lint", [], {})[-1] == "."
    assert command_for("medir", [], {})[-1] == "."


def test_an_unknown_command_is_refused() -> None:
    with pytest.raises(Refused):
        command_for("rm", [], {})


def test_long_output_keeps_the_end_and_says_what_was_left_out() -> None:
    text = "\n".join(str(number) for number in range(200))
    shown = tail(text, 10).splitlines()
    assert shown[0] == "[... 190 linhas anteriores omitidas]"
    assert shown[-1] == "199"
    assert len(shown) == 11
    assert tail("curto", 10) == "curto"


def test_the_usage_is_shown_without_a_command(capsys: pytest.CaptureFixture[str]) -> None:
    assert run_facade([], Path.cwd(), {}) == 2
    assert "uso:" in capsys.readouterr().out


def test_lint_runs_and_returns_the_exit_code_of_the_tool(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "ok.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "bad.py").write_text("import os\n", encoding="utf-8")
    assert run_facade(["lint", "ok.py"], tmp_path, {}) == 0
    assert run_facade(["lint", "bad.py"], tmp_path, {}) != 0
    assert "F401" in capsys.readouterr().out
