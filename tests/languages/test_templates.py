"""The template of each language: what the scaffold writes is a project its adapter recognises,
and (with the tools installed) one that builds and passes its own test."""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from forja.cli.scaffold import project_template, template_adapters
from forja.cli.session import languages
from forja.core.adapters import GITATTRIBUTES, FileClass, valid_project_name

NAMES = ("tool", "my-tool", "a1-b2-c3")


def write(root: Path, language: str, name: str) -> None:
    for relative, text in project_template(language, name).files.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8", newline="\n")


def test_the_five_languages_have_a_template() -> None:
    assert sorted(template_adapters()) == ["csharp", "go", "java", "python", "typescript"]


@pytest.mark.parametrize("language", sorted(template_adapters()))
@pytest.mark.parametrize("name", NAMES)
def test_a_template_is_a_project_its_adapter_detects(
    language: str, name: str, tmp_path: Path
) -> None:
    write(tmp_path, language, name)
    found = [adapter.language for adapter, _ in languages(tmp_path).detect_all(tmp_path)]
    assert found and set(found) == {language}


@pytest.mark.parametrize("language", sorted(template_adapters()))
def test_a_template_ignores_what_a_build_leaves_and_fixes_line_endings(language: str) -> None:
    files = project_template(language, "tool").files
    assert files[".gitattributes"] == GITATTRIBUTES
    assert files[".gitignore"].strip()


@pytest.mark.parametrize("language", sorted(template_adapters()))
def test_a_template_has_a_test_and_code_its_adapter_tells_apart(language: str) -> None:
    adapter = template_adapters()[language]
    kinds = {adapter.classify(path) for path in project_template(language, "my-tool").files}
    assert {FileClass.TEST, FileClass.PRODUCTION} <= kinds


@pytest.mark.parametrize("name", NAMES)
def test_the_names_used_here_are_project_names(name: str) -> None:
    assert valid_project_name(name)


def run(argv: list[str], root: Path) -> None:
    done = subprocess.run(argv, cwd=root, capture_output=True, text=True, timeout=600, check=False)
    assert done.returncode == 0, done.stdout[-1500:] + done.stderr[-1500:]


@pytest.mark.slow
def test_the_python_project_passes_its_test(tmp_path: Path) -> None:
    write(tmp_path, "python", "my-tool")
    run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"], tmp_path)


@pytest.mark.slow
@pytest.mark.skipif(shutil.which("go") is None, reason="the Go tool chain is not installed")
def test_the_go_project_passes_its_test(tmp_path: Path) -> None:
    write(tmp_path, "go", "my-tool")
    run(["go", "vet", "./..."], tmp_path)
    run(["go", "test", "./..."], tmp_path)


@pytest.mark.slow
@pytest.mark.skipif(shutil.which("dotnet") is None, reason="the .NET SDK is not installed")
def test_the_csharp_project_passes_its_test(tmp_path: Path) -> None:
    write(tmp_path, "csharp", "my-tool")
    run(["dotnet", "test"], tmp_path)


@pytest.mark.slow
@pytest.mark.skipif(shutil.which("mvn") is None, reason="Maven is not installed")
def test_the_java_project_passes_its_test(tmp_path: Path) -> None:
    write(tmp_path, "java", "my-tool")
    run([shutil.which("mvn") or "mvn", "-q", "-B", "test"], tmp_path)


@pytest.mark.slow
@pytest.mark.skipif(shutil.which("npm") is None, reason="npm is not installed")
def test_the_typescript_project_passes_its_test_after_the_setup(tmp_path: Path) -> None:
    write(tmp_path, "typescript", "my-tool")
    for argv in project_template("typescript", "my-tool").setup:
        run([shutil.which(argv[0]) or argv[0], *argv[1:]], tmp_path)
    run([shutil.which("npm") or "npm", "test"], tmp_path)
    run([shutil.which("npm") or "npm", "run", "build"], tmp_path)
