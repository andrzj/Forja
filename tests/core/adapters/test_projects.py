from pathlib import Path

import pytest

from forja.core.adapters import AdapterRegistry
from forja.core.adapters.language import Detection
from forja.core.adapters.projects import IGNORED_DIRECTORIES, find_projects, project_directories
from tests.core.adapters.fakes import FakeLanguageAdapter


class GoAdapter(FakeLanguageAdapter):
    language = "go"

    def detect(self, root: Path) -> Detection | None:
        if not (root / "go.mod").is_file():
            return None
        return Detection("go", (".",), ("go.mod",))


def _touch(root: Path, name: str) -> None:
    (root / name).parent.mkdir(parents=True, exist_ok=True)
    (root / name).write_text("")


def test_the_root_comes_first_and_the_directories_below_follow_in_sorted_order(
    tmp_path: Path,
) -> None:
    for name in ("b", "a/z", "a/y"):
        (tmp_path / name).mkdir(parents=True)

    found = [p.relative_to(tmp_path).as_posix() for p in project_directories(tmp_path)]

    assert found == [".", "a", "a/y", "a/z", "b"]


@pytest.mark.parametrize("ignored", sorted(IGNORED_DIRECTORIES) + [".venv", ".hidden"])
def test_dependencies_build_output_and_hidden_directories_are_not_searched(
    tmp_path: Path, ignored: str
) -> None:
    _touch(tmp_path, f"{ignored}/inner/go.mod")
    _touch(tmp_path, "keep/go.mod")

    found = find_projects(GoAdapter(), tmp_path)

    assert [d.roots for d in found] == [("keep",)]


def test_a_manifest_at_every_depth_is_a_project_and_roots_names_its_directory(
    tmp_path: Path,
) -> None:
    for name in ("go.mod", "svc/api/go.mod", "svc/worker/go.mod"):
        _touch(tmp_path, name)

    found = find_projects(GoAdapter(), tmp_path)

    assert [d.roots for d in found] == [(".",), ("svc/api",), ("svc/worker",)]
    assert all(d.language == "go" and d.manifests == ("go.mod",) for d in found)


def test_detect_all_reports_one_entry_per_manifest_directory_in_registration_order(
    tmp_path: Path,
) -> None:
    registry = AdapterRegistry()
    registry.register_language(FakeLanguageAdapter())
    registry.register_language(GoAdapter())
    for name in ("go.mod", "tools/pyproject.toml", "svc/go.mod"):
        _touch(tmp_path, name)

    found = [(d.language, d.roots) for _, d in registry.detect_all(tmp_path)]

    assert found == [("python", ("tools",)), ("go", (".",)), ("go", ("svc",))]
