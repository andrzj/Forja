"""The files of a new Python project: ``pyproject.toml``, a package under ``src`` and one test."""

from forja.core.adapters import GITATTRIBUTES, ProjectTemplate

GITIGNORE = """\
__pycache__/
*.pyc
.venv/
.pytest_cache/
target/
"""


def template(name: str) -> ProjectTemplate:
    package = name.replace("-", "_")
    return ProjectTemplate(
        {
            "pyproject.toml": f"""\
[project]
name = "{name}"
version = "0.1.0"
requires-python = ">=3.12"

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
""",
            f"src/{package}/__init__.py": f'"""{name}."""\n\n__version__ = "0.1.0"\n',
            f"tests/test_{package}.py": f"""\
import {package}


def test_the_package_has_a_version():
    assert {package}.__version__ == "0.1.0"
""",
            ".gitignore": GITIGNORE,
            ".gitattributes": GITATTRIBUTES,
        }
    )
