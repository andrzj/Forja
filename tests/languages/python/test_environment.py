"""The virtual environment of a run: it sees what the repository's interpreter has, and what is
installed in it stays out of that interpreter."""

import asyncio
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from forja.languages.python.environment import (
    EnvironmentFailed,
    RunEnvironment,
    VirtualEnvironment,
)
from forja.languages.python.manifest import declared_requirements

PACKAGE = "forjaprobe"


def _wheel(directory: Path) -> None:
    """A wheel with one module, so installing needs no network."""
    dist = f"{PACKAGE}-1.0.dist-info"
    files = {
        f"{PACKAGE}.py": "VALUE = 7\n",
        f"{dist}/METADATA": f"Metadata-Version: 2.1\nName: {PACKAGE}\nVersion: 1.0\n",
        f"{dist}/WHEEL": (
            "Wheel-Version: 1.0\nGenerator: test\nRoot-Is-Purelib: true\nTag: py3-none-any\n"
        ),
    }
    records = "".join(f"{name},,\n" for name in files) + f"{dist}/RECORD,,\n"
    directory.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(directory / f"{PACKAGE}-1.0-py3-none-any.whl", "w") as wheel:
        for name, text in files.items():
            wheel.writestr(name, text)
        wheel.writestr(f"{dist}/RECORD", records)


def _environment(tmp_path: Path, *, find_links: Path | None = None) -> VirtualEnvironment:
    env = dict(os.environ)
    env["PIP_NO_INDEX"] = "1"
    if find_links is not None:
        env["PIP_FIND_LINKS"] = str(find_links)
    return VirtualEnvironment(
        tmp_path / "work" / "venv",
        base_python=sys.executable,
        env=env,
        timeout=300,
        log_dir=tmp_path / "logs",
    )


def _imports(python: tuple[str, ...], module: str) -> bool:
    done = subprocess.run([*python, "-c", f"import {module}"], capture_output=True, check=False)
    return done.returncode == 0


def test_the_environment_has_its_own_interpreter_and_sees_the_base_packages(tmp_path: Path) -> None:
    environment = _environment(tmp_path)

    asyncio.run(environment.create())

    assert Path(environment.python[0]).is_file()
    assert Path(environment.python[0]) != Path(sys.executable)
    assert _imports(environment.python, "pytest")  # the base interpreter has it


def test_an_editable_install_of_a_src_layout_repository_stays_visible(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    (repository / "src" / "srcprobe").mkdir(parents=True)
    (repository / "src" / "srcprobe" / "__init__.py").write_text("", encoding="utf-8")
    base = tmp_path / "base"
    subprocess.run([sys.executable, "-m", "venv", str(base)], check=True, capture_output=True)
    base_python = base / ("Scripts" if sys.platform == "win32" else "bin")
    base_python /= "python.exe" if sys.platform == "win32" else "python"
    purelib = subprocess.run(
        [str(base_python), "-c", "import sysconfig; print(sysconfig.get_path('purelib'))"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    # what `pip install -e` leaves in the packages of the interpreter of a src-layout repository
    (Path(purelib) / "__editable__.srcprobe.pth").write_text(
        str(repository / "src") + "\n", encoding="utf-8"
    )
    assert _imports((str(base_python),), "srcprobe")
    _wheel(tmp_path / "wheels")
    env = dict(os.environ, PIP_NO_INDEX="1", PIP_FIND_LINKS=str(tmp_path / "wheels"))
    environment = VirtualEnvironment(
        tmp_path / "work" / "venv",
        base_python=str(base_python),
        env=env,
        timeout=300,
        log_dir=tmp_path / "logs",
    )

    asyncio.run(environment.create())
    asyncio.run(environment.install([PACKAGE]))

    assert _imports(environment.python, "srcprobe")
    assert _imports(environment.python, PACKAGE)


def test_a_package_installed_stays_in_the_environment(tmp_path: Path) -> None:
    _wheel(tmp_path / "wheels")
    environment = _environment(tmp_path, find_links=tmp_path / "wheels")
    asyncio.run(environment.create())
    assert not _imports(environment.python, PACKAGE)

    asyncio.run(environment.install({PACKAGE}))

    assert _imports(environment.python, PACKAGE)
    assert not _imports((sys.executable,), PACKAGE)


def test_what_is_installed_is_not_installed_again(tmp_path: Path) -> None:
    _wheel(tmp_path / "wheels")
    environment = _environment(tmp_path, find_links=tmp_path / "wheels")
    asyncio.run(environment.create())
    asyncio.run(environment.install({PACKAGE}))

    (tmp_path / "wheels" / f"{PACKAGE}-1.0-py3-none-any.whl").unlink()  # a second run would fail
    asyncio.run(environment.install({PACKAGE}))
    asyncio.run(environment.install(set()))

    assert environment.installed == {PACKAGE}


def test_a_package_that_cannot_be_installed_is_reported_with_the_installer_output(
    tmp_path: Path,
) -> None:
    environment = _environment(tmp_path)
    asyncio.run(environment.create())

    with pytest.raises(EnvironmentFailed, match="pip install") as error:
        asyncio.run(environment.install({"forja-no-such-package"}))

    assert "forja-no-such-package" in str(error.value)
    assert environment.installed == frozenset()


def test_a_base_interpreter_that_does_not_exist_is_reported(tmp_path: Path) -> None:
    environment = VirtualEnvironment(
        tmp_path / "work" / "venv",
        base_python=str(tmp_path / "no-python"),
        env=dict(os.environ),
        timeout=30,
        log_dir=tmp_path / "logs",
    )

    with pytest.raises(EnvironmentFailed, match="spawn_failed"):
        asyncio.run(environment.create())


def test_requirements_are_read_whole_from_both_manifests() -> None:
    pyproject = (
        '[project]\nname = "x"\n'
        'dependencies = ["slugify>=1.0", "rich[extra] ; python_version>\'3\'"]\n'
        '[project.optional-dependencies]\ndev = ["pytest"]\n'
        '[dependency-groups]\ndocs = ["mkdocs", {include-group = "dev"}]\n'
    )
    requirements = "# tools\nrequests==2.0  # pinned\n--index-url https://x\n-r other.txt\n"

    assert declared_requirements("pyproject.toml", pyproject) == {
        "slugify>=1.0",
        "rich[extra] ; python_version>'3'",
        "pytest",
        "mkdocs",
    }
    assert declared_requirements("sub/requirements-dev.txt", requirements) == {"requests==2.0"}


def test_requirements_that_are_not_plain_are_left_out_and_other_files_have_none() -> None:
    text = "good\nbad @ https://x/y.whl\n./local\npkg-1.0.whl\n"

    assert declared_requirements("requirements.txt", text) == {"good"}
    assert declared_requirements("go.mod", "good") == frozenset()
    with pytest.raises(ValueError, match="not valid TOML"):
        declared_requirements("pyproject.toml", "= =")


def test_the_environment_is_made_in_a_directory_whose_parents_do_not_exist(tmp_path: Path) -> None:
    environment = VirtualEnvironment(
        tmp_path / "a" / "b" / "venv",
        base_python=sys.executable,
        env=dict(os.environ),
        timeout=300,
        log_dir=tmp_path / "logs",
    )

    asyncio.run(environment.create())

    assert environment.ready


def test_an_environment_can_be_made_again_over_the_same_parent(tmp_path: Path) -> None:
    environment = _environment(tmp_path)
    asyncio.run(environment.create())

    asyncio.run(environment.create())

    assert environment.ready


def test_each_command_has_a_numbered_log_from_one(tmp_path: Path) -> None:
    environment = _environment(tmp_path)

    asyncio.run(environment.create())

    logs = sorted(path.name for path in (tmp_path / "logs").iterdir())
    assert logs == ["venv-1.log", "venv-2.log", "venv-3.log"]


def test_the_package_directory_is_the_last_line_the_interpreter_prints(tmp_path: Path) -> None:
    (tmp_path / "noise").mkdir()
    (tmp_path / "noise" / "sitecustomize.py").write_text("print('noise')\n", encoding="utf-8")
    noisy = dict(os.environ, PYTHONPATH=str(tmp_path / "noise"))  # it says more before the answer
    environment = VirtualEnvironment(
        tmp_path / "work" / "venv",
        base_python=sys.executable,
        env=noisy,
        timeout=300,
        log_dir=tmp_path / "logs",
    )

    asyncio.run(environment.create())

    assert _imports(environment.python, "pytest")


def test_a_run_uses_the_repository_interpreter_until_it_has_an_environment(tmp_path: Path) -> None:
    environment = _environment(tmp_path)
    run = RunEnvironment(environment, (sys.executable,))
    assert run.python == (sys.executable,)

    assert asyncio.run(run.install(set())) is None

    assert run.python == environment.python
    assert environment.ready


def test_a_run_environment_says_why_an_installation_failed(tmp_path: Path) -> None:
    run = RunEnvironment(_environment(tmp_path), (sys.executable,))

    failure = asyncio.run(run.install({"forja-no-such-package"}))

    assert failure is not None and "forja-no-such-package" in failure
