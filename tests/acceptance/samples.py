"""Three small Python repositories, each with one function the Forja should simplify.

They differ on purpose: a plain function, a function among several modules that call each other,
and a method of a class. For each one the stand-in agent knows the simplified version, so a run can
be followed from the command to the delivered branch. The files are written in the canonical format
of the formatter, because the format gate would refuse anything else.
"""

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from tests.cli.test_main import git

NL = chr(10)
BRANCHES = 18  # a chain this long is well above the complexity limit


def canonical(text: str) -> str:
    done = subprocess.run(
        [sys.executable, "-m", "ruff", "format", "--stdin-filename", "x.py", "-"],
        input=text, capture_output=True, text=True, check=True, encoding="utf-8",
    )  # fmt: skip
    return done.stdout


def chain(name: str, args: str, subject: str, indent: str = "    ") -> str:
    """A function that is a chain of ``elif`` on ``subject``: easy to read, expensive to measure."""
    lines = [f"{indent}def {name}({args}):"] if indent else [f"def {name}({args}):"]
    pad = indent * 2 if indent else "    "
    for number in range(BRANCHES):
        keyword = "if" if number == 0 else "elif"
        lines += [f"{pad}{keyword} {subject} == {number}:", f'{pad}    return "v{number}"']
    lines.append(f'{pad}return "other"')
    return NL.join(lines) + NL


def table(name: str, args: str, subject: str) -> str:
    entries = "".join(f'    {number}: "v{number}",{NL}' for number in range(BRANCHES))
    head = f"VALUES = {{{NL}{entries}}}{NL}{NL}{NL}"
    return head + f'def {name}({args}):{NL}    return VALUES.get({subject}, "other"){NL}'


@dataclass(frozen=True)
class Sample:
    name: str
    files: dict[str, str]
    target: str  # the file the planner will pick and the agent will rewrite
    after: str  # the simplified file
    marker: str  # what the delivered file must contain


SAMPLES: dict[str, Sample] = {}

SAMPLES["a plain function"] = Sample(
    name="a plain function",
    files={
        "pyproject.toml": '[project]\nname = "plain"\nversion = "0"\n\n[tool.pytest.ini_options]\n'
        'pythonpath = ["src"]\n',
        "src/plain/__init__.py": "",
        "src/plain/mod.py": canonical(chain("label", "n", "n", indent="")),
        "tests/test_mod.py": canonical(
            "from plain.mod import label\n\n\ndef test_label():\n"
            f"    assert [label(n) for n in range({BRANCHES + 2})] == "
            f"[f'v{{n}}' for n in range({BRANCHES})] + ['other', 'other']\n"
        ),
    },
    target="src/plain/mod.py",
    after=canonical(table("label", "n", "n")),
    marker="VALUES",
)

SAMPLES["several modules"] = Sample(
    name="several modules",
    files={
        "pyproject.toml": '[project]\nname = "shop"\nversion = "0"\n\n[tool.pytest.ini_options]\n'
        'pythonpath = ["src"]\n',
        "src/shop/__init__.py": "from shop.pricing import tier\nfrom shop.tax import add_tax\n",
        "src/shop/tax.py": canonical("def add_tax(value):\n    return round(value * 1.1, 2)\n"),
        "src/shop/cart.py": canonical(
            "from shop.pricing import tier\nfrom shop.tax import add_tax\n\n\n"
            "def total(prices, level):\n"
            "    return add_tax(sum(prices)) if tier(level) != 'v0' else sum(prices)\n"
        ),
        "src/shop/pricing.py": canonical(chain("tier", "level", "level", indent="")),
        "tests/test_shop.py": canonical(
            "from shop import add_tax, tier\nfrom shop.cart import total\n\n\n"
            "def test_tier():\n"
            f"    assert [tier(n) for n in range({BRANCHES + 1})] == "
            f"[f'v{{n}}' for n in range({BRANCHES})] + ['other']\n\n\n"
            "def test_tax_and_cart():\n"
            "    assert add_tax(10) == 11.0\n"
            "    assert total([1, 2], 0) == 3\n"
            "    assert total([10], 1) == 11.0\n"
        ),
    },
    target="src/shop/pricing.py",
    after=canonical(table("tier", "level", "level")),
    marker="VALUES",
)

_METHOD = chain("route", "self, code", "code", indent="    ")
SAMPLES["a method"] = Sample(
    name="a method",
    files={
        "pyproject.toml": '[project]\nname = "web"\nversion = "0"\n\n[tool.pytest.ini_options]\n'
        'pythonpath = ["src"]\n',
        "src/web/__init__.py": "",
        "src/web/router.py": canonical("class Router:\n" + _METHOD),
        "tests/test_router.py": canonical(
            "import pytest\n\nfrom web.router import Router\n\n\n"
            f"@pytest.mark.parametrize('code', range({BRANCHES + 2}))\n"
            "def test_route(code):\n"
            "    expected = f'v{code}' if code < " + str(BRANCHES) + " else 'other'\n"
            "    assert Router().route(code) == expected\n"
        ),
    },
    target="src/web/router.py",
    after=canonical(
        "VALUES = {"
        + NL
        + "".join(f'    {n}: "v{n}",{NL}' for n in range(BRANCHES))
        + "}"
        + NL * 3
        + "class Router:"
        + NL
        + "    def route(self, code):"
        + NL
        + '        return VALUES.get(code, "other")'
        + NL
    ),
    marker="VALUES",
)


def build(sample: Sample, root: Path) -> Path:
    repo = root / "sample"
    for relative, text in sample.files.items():
        target = repo / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8", newline=NL)
    git(repo, "init", "-q", "-b", "main")
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", "init")
    return repo
