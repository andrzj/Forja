"""The graph between directories: the edges each language gives, the cycles and the metrics.

The edges of the fixtures for Go, Java and TypeScript are the ones the reference tools gave on the
same files (``go list``, ``jdeps``, ``dependency-cruiser``); Python was compared with ``grimp`` on
Forja itself.
"""

import pytest

from forja.checks.architecture import Unavailable, build
from forja.checks.architecture.facts import read_file
from forja.checks.architecture.go import module_path
from forja.checks.structure import SyntaxProblem


def edges(language, files, go_mod=None):
    return set(build(language, files, go_mod).edges)


def test_python_resolves_absolute_relative_and_from_imports():
    files = {
        "pkg/__init__.py": "",
        "pkg/a/__init__.py": "from pkg.b import x\n",
        "pkg/b/__init__.py": "x = 1\n",
        "pkg/b/m.py": (
            "from typing import TYPE_CHECKING\n"
            "from pkg.a.zz import w\n"
            "from . import x\n"
            "if TYPE_CHECKING:\n"
            "    from ..a import q\n"
            "def f():\n"
            "    import pkg.a\n"
        ),
        "pkg/a/zz.py": "w = 1\n",
    }
    assert edges("python", files) == {("pkg/a", "pkg/b"), ("pkg/b", "pkg/a")}


def test_python_import_of_a_name_falls_back_to_the_package():
    files = {
        "src/p/__init__.py": "",
        "src/p/core/__init__.py": "class State: ...\n",
        "src/p/cli/__init__.py": "",
        "src/p/cli/run.py": "from p.core import State\nfrom p.core.nothing import Other\n",
    }
    assert edges("python", files) == {("src/p/cli", "src/p/core")}


def test_python_ignores_what_is_not_in_the_project():
    files = {"p/__init__.py": "import os\nimport requests.adapters\nfrom .. import top\n"}
    assert edges("python", files) == set()


def test_python_files_outside_a_package_are_modules_of_their_folder():
    files = {"tools/a.py": "import b\n", "tools/b.py": "", "lib/c.py": "import a\n"}
    assert edges("python", files) == {("lib", "tools")}


def test_go_follows_the_module_path_and_skips_the_rest():
    files = {
        "a/a.go": 'package a\nimport (\n  "fmt"\n  "ex.com/m/b"\n  "github.com/x/y"\n)\n',
        "a/sub/s.go": "package sub\n",
        "b/b.go": 'package b\nimport "ex.com/m/a/sub"\nimport "ex.com/m/nothing"\n',
        "main.go": 'package main\nimport _ "ex.com/m/a"\n',
    }
    go_mod = "module ex.com/m\n\ngo 1.21\n"
    assert edges("go", files, go_mod) == {("a", "b"), ("b", "a/sub"), (".", "a")}


def test_go_needs_a_module_path():
    with pytest.raises(Unavailable):
        build("go", {"a/a.go": "package a\n"}, "go 1.21\n")
    with pytest.raises(Unavailable):
        build("go", {"a/a.go": "package a\n"}, None)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("module ex.com/m\n", "ex.com/m"),
        ('module "ex.com/m"\n', "ex.com/m"),
        ("// c\n\n  module   ex.com/m  // x\n", "ex.com/m"),
        ("go 1.21\n", None),
    ],
)
def test_module_path(text, expected):
    assert module_path(text) == expected


JAVA = {
    "src/p/a/A.java": "package p.a;\nimport p.b.B;\npublic class A { B b; }",
    "src/p/b/B.java": "package p.b;\nimport p.c.*;\npublic class B { C c; }",
    "src/p/c/C.java": "package p.c;\npublic class C { p.a.A a; }",
    "src/p/c/I.java": "package p.c;\npublic interface I {}",
}


def test_java_matches_imports_with_declared_packages_and_types():
    # jdeps also shows p.c -> p.a, which the source reaches by a qualified name, not an import
    assert edges("java", JAVA) == {("src/p/a", "src/p/b"), ("src/p/b", "src/p/c")}


def test_java_reaches_a_type_through_a_member_or_a_nested_type():
    files = {
        "a/A.java": "package a;\nimport static b.B.helper;\nimport b.B.Inner;\nclass A {}",
        "b/B.java": "package b;\npublic class B { public static class Inner {} }",
        "c/C.java": "class C {}",
        "d/D.java": "package d;\nimport java.util.List;\nimport c.C;\nclass D {}",
    }
    assert edges("java", files) == {("a", "b")}


def test_java_package_split_over_directories_gives_an_edge_to_each():
    files = {
        "x/A.java": "package p;\nclass A {}",
        "y/B.java": "package p;\nclass B {}",
        "z/C.java": "package q;\nimport p.*;\nclass C {}",
    }
    assert edges("java", files) == {("z", "x"), ("z", "y")}


def test_csharp_matches_usings_with_declared_namespaces():
    files = {
        "A/A.cs": "using B.Inner;\nusing System;\nusing static C.Util;\nnamespace A { class X {} }",
        "B/B.cs": "namespace B { namespace Inner { class Y {} } }",
        "C/C.cs": "namespace C;\nusing A;\nclass Util {}",
        "D/D.cs": "using Alias = B.Inner.Y;\nnamespace D { class Z {} }",
    }
    assert edges("csharp", files) == {("A", "B"), ("A", "C"), ("C", "A"), ("D", "B")}


TS = {
    "src/a/a.ts": "import { b } from '../b/b';\nimport * as fs from 'fs';\n",
    "src/b/b.ts": "import { c } from '@c/c';\nimport { d } from '../c';\n",
    "src/c/c.ts": "import type { a } from '../a/a';\n",
    "src/c/index.ts": "const x = () => import('../a/a');\n",
}


def test_typescript_follows_relative_specifiers_only():
    assert edges("typescript", TS) == {
        ("src/a", "src/b"),
        ("src/b", "src/c"),
        ("src/c", "src/a"),
    }


def test_typescript_does_not_resolve_a_path_alias():
    only_alias = {"src/b/b.ts": "import { c } from '@c/c';\n", "src/c/c.ts": ""}
    assert edges("typescript", only_alias) == set()


def test_script_resolves_extensions_index_and_compiled_names():
    files = {
        "a/main.js": "import './x.js';\nimport './dir';\nimport '../out';\nimport './gone';\n",
        "a/x.ts": "",
        "a/dir/index.jsx": "",
        "lib/m.mjs": "import '../a/main';\nimport '..';\n",
        "index.ts": "",
    }
    assert edges("javascript", files) == {("a", "a/dir"), ("lib", "a"), ("lib", ".")}


def test_a_specifier_that_leaves_the_project_is_not_an_edge():
    files = {"a.ts": "import '../../x';\n", "b/c.ts": "import '../../..';\n"}
    assert edges("typescript", files) == set()


def test_cycles_are_groups_of_directories_that_depend_on_each_other():
    files = {
        "a/__init__.py": "import b\nimport c\n",
        "b/__init__.py": "import a\n",
        "c/__init__.py": "import d\n",
        "d/__init__.py": "import e\n",
        "e/__init__.py": "import c\nimport f\n",
        "f/__init__.py": "",
    }
    graph = build("python", files)
    assert graph.cycles() == (frozenset({"a", "b"}), frozenset({"c", "d", "e"}))
    assert graph.path_in(frozenset({"c", "d", "e"})) == ["c", "d", "e", "c"]
    assert graph.path_in(frozenset({"a", "b"})) == ["a", "b", "a"]


def test_a_directory_is_not_its_own_dependency():
    graph = build("python", {"a/m.py": "import n\n", "a/n.py": "", "b/k.py": "import a.m\n"})
    assert graph.edges == frozenset()
    assert graph.cycles() == ()


def test_a_long_chain_does_not_hit_a_recursion_limit():
    size = 3000
    files = {f"d{i}/__init__.py": f"import d{i + 1}\n" for i in range(size)}
    files[f"d{size}/__init__.py"] = "import d0\n"
    (group,) = build("python", files).cycles()
    assert len(group) == size + 1


def test_metrics_follow_martin():
    files = {
        "api/__init__.py": "from abc import ABC\nclass Port(ABC): ...\nclass Other(ABC): ...\n",
        "impl/__init__.py": "import api\nclass A(api.Port): ...\nclass B: ...\n",
        "use/__init__.py": "import api\nimport impl\n",
    }
    graph = build("python", files)
    api = graph.metrics("api")
    assert (api.afferent, api.efferent, api.instability) == (2, 0, 0.0)
    assert (api.abstractness, api.distance, api.types) == (1.0, 0.0, 2)
    impl = graph.metrics("impl")
    assert (impl.afferent, impl.efferent, impl.instability) == (1, 1, 0.5)
    assert (impl.abstractness, impl.distance) == (0.0, 0.5)
    use = graph.metrics("use")
    assert (use.instability, use.abstractness, use.distance, use.types) == (1.0, 0.0, 0.0, 0)


def test_a_directory_with_no_edge_and_no_type_is_at_distance_one():
    metrics = build("python", {"a/x.py": "y = 1\n"}).metrics("a")
    assert (metrics.instability, metrics.abstractness, metrics.distance) == (0.0, 0.0, 1.0)


def test_files_that_do_not_parse_stay_out_and_are_named():
    graph = build("python", {"a/ok.py": "x = 1\n", "a/bad.py": "def (:\n"})
    assert graph.unreadable == ("a/bad.py",)
    assert graph.nodes == frozenset({"a"})


def test_nothing_to_read_is_unavailable():
    with pytest.raises(Unavailable):
        build("python", {})
    with pytest.raises(Unavailable):
        build("python", {"a/bad.py": "def (:\n", "notes.txt": "x"})


ABSTRACT_METHOD = (
    "class A:\n    @abc.abstractmethod\n    def f(self): ...\nclass B:\n    def g(self): ...\n"
)
JAVA_TYPES = (
    "package p;\npublic abstract class A {}\ninterface I {}\nenum E { X }\n"
    "record R(int a) {}\nclass C {}"
)
CSHARP_TYPES = (
    "abstract class A {}\ninterface I {}\nstruct S {}\nrecord R(int a);\nenum E { X }\nclass C {}"
)


@pytest.mark.parametrize(
    ("path", "source", "abstract", "types"),
    [
        ("a.py", "class A(ABC): ...\nclass B(typing.Protocol[T]): ...\nclass C: ...\n", 2, 3),
        ("a.py", ABSTRACT_METHOD, 1, 2),
        ("a.py", "class Abstract: ...\nclass ABCD: ...\n", 0, 2),
        ("a.go", "package a\ntype I interface{ F() }\ntype S struct{}\ntype X = int\n", 1, 2),
        ("A.java", JAVA_TYPES, 2, 5),
        ("a.cs", CSHARP_TYPES, 2, 6),
        (
            "a.ts",
            "abstract class A {}\ninterface I {}\nenum E { X }\nclass C {}\ntype T = number;",
            2,
            4,
        ),
        ("a.js", "class A {}\nclass B {}", 0, 2),
    ],
)
def test_abstract_types_by_language(path, source, abstract, types):
    found = read_file(path, source)
    assert (found.abstract, found.types) == (abstract, types)


def test_declared_names_of_java_and_csharp():
    java = read_file("A.java", "package p.q;\nclass A {}\ninterface B {}")
    assert java.declared == ("p.q", "p.q.A", "p.q.B")
    assert read_file("A.java", "class A {}").declared == ("", "A")
    nested = "namespace A.B { namespace C { class X {} } }\nnamespace D;\n"
    assert read_file("a.cs", nested).declared == ("A.B", "A.B.C", "D")


def test_a_text_that_does_not_parse_raises_for_the_reader():
    with pytest.raises(SyntaxProblem):
        read_file("a.py", "def (:\n")
    assert read_file("a.rb", "puts 1") is None
