"""The readers of what a file imports: the target as written, wherever the import stands."""

import pytest

from forja.checks.structure import SyntaxProblem, imports_of


def test_python_names_every_module_an_import_reaches() -> None:
    source = (
        "import a.b as c, d\n"
        "from . import x\n"
        "from ..a import q, r as s\n"
        "from m import *\n"
        "from n.o import p\n"
        "from __future__ import annotations\n"
    )
    assert imports_of("a.py", source) == ("a.b", "d", ".x", "..a.q", "..a.r", "m", "n.o.p")


def test_python_sees_imports_inside_functions_and_under_type_checking() -> None:
    source = (
        "from typing import TYPE_CHECKING\n"
        "if TYPE_CHECKING:\n"
        "    from ..a import q\n"
        "def f():\n"
        "    import z\n"
    )
    assert imports_of("a.py", source) == ("typing.TYPE_CHECKING", "..a.q", "z")


def test_go_gives_the_path_without_quotes_for_every_form_of_import() -> None:
    source = (
        'package a\nimport (\n  "fmt"\n  x "ex.com/m/b"\n  _ "ex.com/m/c"\n  . "ex.com/m/d"\n)\n'
        'import "os"\nimport `ex.com/m/raw`\n'
    )
    assert imports_of("a.go", source) == (
        "fmt",
        "ex.com/m/b",
        "ex.com/m/c",
        "ex.com/m/d",
        "os",
        "ex.com/m/raw",
    )


def test_java_keeps_the_wildcard_and_the_member_of_a_static_import() -> None:
    source = "package p;\nimport a.b.C;\nimport a.b.*;\nimport static a.B.m;\nclass A {}"
    assert imports_of("A.java", source) == ("a.b.C", "a.b.*", "a.B.m")


def test_csharp_gives_the_target_of_every_form_of_using() -> None:
    source = (
        "global using G.H;\nusing A.B;\nusing static C.D;\nusing X = E.F;\nusing Single;\n"
        "namespace N { using Q.R; }\n"
    )
    assert imports_of("a.cs", source) == ("G.H", "A.B", "C.D", "E.F", "Single", "Q.R")


def test_csharp_ignores_a_using_statement_that_disposes() -> None:
    source = "class A { void F() { using (var s = Open()) { } using var t = Open(); } }"
    assert imports_of("a.cs", source) == ()


TS = (
    "import {a} from '../b';\n"
    "import * as f from 'fs';\n"
    "import type {t} from './t';\n"
    "export {z} from './z';\n"
    "export * from './w';\n"
    "import q = require('./q');\n"
    "const l = () => import('./l');\n"
    "const r = require('./r');\n"
    "const v = require(name);\n"
    "const u = import(`./${name}`);\n"
    "import './side';\n"
)
TS_EXPECTED = ("../b", "fs", "./t", "./z", "./w", "./q", "./l", "./r", "./side")


@pytest.mark.parametrize("path", ["a.ts", "a.tsx"])
def test_typescript_names_literal_specifiers_of_every_kind(path: str) -> None:
    assert sorted(imports_of(path, TS) or ()) == sorted(TS_EXPECTED)


def test_javascript_reads_imports_and_requires() -> None:
    source = "import a from './a';\nexport { b } from \"./b\";\nconst c = require('./c');\n"
    assert imports_of("a.js", source) == ("./a", "./b", "./c")


def test_a_call_of_another_name_is_not_an_import() -> None:
    assert imports_of("a.js", "load('./x'); a.require('./y'); import('./a', 'b');") == ()


def test_a_file_without_imports_names_none() -> None:
    assert imports_of("a.py", "x = 1\n") == ()


def test_a_language_not_read_has_no_imports() -> None:
    assert imports_of("a.rb", "require 'x'") is None


def test_text_that_does_not_parse_is_a_syntax_problem() -> None:
    with pytest.raises(SyntaxProblem):
        imports_of("a.py", "import (")
