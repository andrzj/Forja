from pathlib import Path

from forja.cli.session import languages, repo_python


def interpreter_of(registry: object) -> tuple[str, ...]:
    project = registry.project("python")  # type: ignore[attr-defined]
    return project._adapter._python  # type: ignore[no-any-return]


def test_a_python_project_uses_the_interpreter_the_run_gives_it_when_it_is_made(
    tmp_path: Path,
) -> None:
    current = [("one",)]
    registry = languages(tmp_path, lambda: current[0])

    assert interpreter_of(registry) == ("one",)
    current[0] = ("two",)
    assert interpreter_of(registry) == ("two",)


def test_without_an_interpreter_from_the_run_a_python_project_uses_the_repositorys(
    tmp_path: Path,
) -> None:
    registry = languages(tmp_path)

    assert interpreter_of(registry) == repo_python(tmp_path)
