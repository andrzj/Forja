import ast
from pathlib import Path

import pytest

from forja.mutation import Site, apply_site, discover

SRC = Path(__file__).resolve().parents[2] / "src" / "forja"


def sites_of(body: str, header: str = "def f(a, b, c=None):") -> list[Site]:
    indented = "".join(f"    {line}\n" for line in body.strip().splitlines())
    return discover(f"{header}\n{indented}")


def changes(body: str) -> list[str]:
    return [site.description for site in sites_of(body)]


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ("return a + b", ["+ -> -"]),
        ("return a - b", ["- -> +"]),
        ("return a * b", ["* -> /"]),
        ("return a / b", ["/ -> *"]),
        ("return a < b", ["< -> <="]),
        ("return a <= b", ["<= -> <"]),
        ("return a > b", ["> -> >="]),
        ("return a >= b", [">= -> >"]),
        ("return a == b", ["== -> !="]),
        ("return a != b", ["!= -> =="]),
        ("return a and b", ["and -> or"]),
        ("return a or b", ["or -> and"]),
        ("return not a", ["delete not"]),
        ("return -a", ["delete -"]),
        ("return True", ["True -> False"]),
        ("return False", ["False -> True"]),
        ("return 0", ["0 -> 1"]),
        ("return 1", ["1 -> 0"]),
    ],
)
def test_each_operator_has_one_change_worded_as_the_mutator_words_it(
    body: str, expected: list[str]
) -> None:
    assert changes(body) == expected


@pytest.mark.parametrize(
    "body",
    [
        "return a // b",
        "return a % b",
        "return a ** b",
        "return a & b",
        "return a | b",
        "return a in b",
        "return a is b",
        "return +a",
        "return ~a",
        "return 2",
        "return 1.0",
        "return 0x1",
        "return 1_0",
        "return 00",
        "return None",
        'return "a + b and True 1"',
        "return a  # + - and not 1",
        "return f(*b, **c)",
        "a += b",
        "a -= 2",
    ],
)
def test_what_the_mutator_does_not_change_is_not_a_site(body: str) -> None:
    assert changes(body) == []


def test_code_outside_a_function_has_no_site() -> None:
    source = "LIMIT = 1\nclass C:\n    FLAG = True\n    def m(self):\n        return 0\n"
    assert [(s.line, s.function) for s in discover(source)] == [(5, "C.m")]


def test_the_name_is_the_qualified_name_of_the_innermost_function() -> None:
    source = (
        "class A:\n"
        "    class B:\n"
        "        def m(self):\n"
        "            def inner():\n"
        "                return 1\n"
        "            return 0\n"
        "def top():\n"
        "    async def work():\n"
        "        return True\n"
    )
    assert [(s.line, s.function) for s in discover(source)] == [
        (5, "A.B.m.inner"),
        (6, "A.B.m"),
        (9, "top.work"),
    ]


def test_decorators_are_outside_the_function_and_defaults_are_inside() -> None:
    source = "@wrap(1)\ndef f(a=1):\n    pass\n"
    assert [(s.line, s.function) for s in discover(source)] == [(2, "f")]


def test_a_lambda_belongs_to_the_function_that_holds_it() -> None:
    assert changes("return lambda x: x + 1") == ["+ -> -", "1 -> 0"]


def test_a_negative_one_has_two_sites() -> None:
    assert changes("return -1") == ["delete -", "1 -> 0"]


def test_every_operator_of_a_chain_is_a_site() -> None:
    assert changes("return a < b <= c") == ["< -> <=", "<= -> <"]
    assert changes("return a and b or c") == ["and -> or", "or -> and"]
    assert changes("return a and b and c") == ["and -> or", "and -> or"]


@pytest.mark.parametrize("body", ["return a not in b", "return a is not b"])
def test_negated_membership_and_identity_lose_the_not_only(body: str) -> None:
    source = f"def f(a, b):\n    {body}\n"
    (site,) = discover(source)
    assert site.description == "delete not"
    assert apply_site(source, site) == source.replace("not", "")


def test_the_operator_is_found_through_parentheses_comments_and_line_breaks() -> None:
    body = "return (\n    (a)  # - and\n    +\n    (b)\n)"
    sites = sites_of(body)
    assert [(s.line, s.description) for s in sites] == [(4, "+ -> -")]


def test_a_binary_minus_before_a_unary_one_is_two_different_sites() -> None:
    assert changes("return a - -b") == ["- -> +", "delete -"]


def test_an_f_string_expression_is_code_and_its_text_is_not() -> None:
    assert changes('return f"a + b {a + b} 1"') == ["+ -> -"]


def test_offsets_are_bytes_of_utf_8_and_lines_are_one_based() -> None:
    source = 'def f(a, b):\n    x = "ção"; return a + b\n'
    (site,) = discover(source)
    assert site.line == 2
    assert source.encode()[site.start : site.end] == b"+"
    assert apply_site(source, site) == 'def f(a, b):\n    x = "ção"; return a - b\n'


def test_sites_come_in_file_order() -> None:
    sites = sites_of("if a > 0:\n    return b + 1\nreturn c")
    assert [(s.line, s.start) for s in sites] == sorted((s.line, s.start) for s in sites)
    assert [s.description for s in sites] == ["> -> >=", "0 -> 1", "+ -> -", "1 -> 0"]


def test_source_that_is_not_python_raises_syntax_error() -> None:
    with pytest.raises(SyntaxError):
        discover("def f(:\n")


def test_apply_refuses_a_site_that_does_not_belong_to_the_source() -> None:
    (site,) = sites_of("return a + b")
    with pytest.raises(ValueError, match="no longer has"):
        apply_site("def f(a, b):\n    return a * b\n", site)


@pytest.mark.parametrize(
    "path", sorted(SRC.rglob("*.py")), ids=lambda p: p.relative_to(SRC).as_posix()
)
def test_every_mutant_of_the_project_is_python_that_differs_from_the_original(path: Path) -> None:
    source = path.read_text(encoding="utf-8")
    for site in discover(source):
        mutant = apply_site(source, site)
        assert mutant != source
        ast.parse(mutant)


SUPPRESSED = [
    ("src/forja/core/redaction/engine.py", "_shorten_long_lines", "<= -> <"),
    ("src/forja/core/redaction/engine.py", "_merge_overlaps", "delete -"),
    ("src/forja/core/redaction/engine.py", "_merge_overlaps", "1 -> 0"),
    ("src/forja/core/redaction/engine.py", "_merge_overlaps", "- -> +"),
    ("src/forja/core/redaction/engine.py", "_merge_overlaps", "> -> >="),
    ("src/forja/ui/plain.py", "PlainRenderer.__init__", "0 -> 1"),
    ("src/forja/core/gitguard/rules.py", "check", "== -> !="),
    ("src/forja/core/policy/config.py", "_check_pattern", "False -> True"),
    ("src/forja/ui/theme.py", "_luminance.channel", "<= -> <"),
    ("src/forja/languages/python/parsers.py", "_summary_lines", "1 -> 0"),
    ("src/forja/ui/plain.py", "PlainRenderer._update_feed", "> -> >="),
    ("src/forja/ui/plain.py", "PlainRenderer._update_rejections", "> -> >="),
    ("src/forja/orchestrator/agent_runner.py", "build_package", "True -> False"),
    ("src/forja/core/process/runner.py", "ProcessRunner._supervise", "0 -> 1"),
    ("src/forja/core/locking/index_locks.py", "remove_orphan_index_locks", "False -> True"),
    ("src/forja/core/gitguard/guarded.py", "GuardedGit.run", "or -> and"),
]


@pytest.mark.parametrize(("file", "function", "change"), SUPPRESSED)
def test_the_changes_the_suppressions_name_are_sites_of_the_engine(
    file: str, function: str, change: str
) -> None:
    source = (SRC.parents[1] / file).read_text(encoding="utf-8")
    assert (function, change) in {(s.function, s.description) for s in discover(source)}
