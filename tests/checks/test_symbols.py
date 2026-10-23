"""The symbols of a source file, read with the real grammars of the six languages."""

import pytest

from forja.checks.symbols import symbols_in

PY = (
    "class A:\n    def m(self): pass\n    def _p(self): pass\n"
    "def f(x): return x\nasync def g(): pass\n"
)
GO = (
    "package p\ntype T struct{}\nfunc (t *T) M() {}\nfunc F(x int) int { return x }\n"
    "func f() {}\ntype I interface{ Do() }\nvar V = 1\n"
)
JAVA = (
    "package p;\npublic class A { public void m() {} private int n(){return 1;}"
    " public interface I { void x(); } record R(int a){} enum E{X} }\n"
)
CS = (
    "namespace P { public class A { public void M() {} private int N() => 1;"
    " public int Prop {get;set;} } public interface I { void X(); } struct S{} }\n"
)
JS = (
    "export function f(x){return x}\nexport const g = (y) => y;\n"
    "class A { m(){} }\nconst h = function(){};\nconst k = 3;\n"
)
TS = (
    "export function f(x: number): number {return x}\n"
    "export class A { m(): void {} private p(): void {} }\n"
    "export interface I { a: number }\nexport type T = number;\nenum E { X }\n"
)


def listed(path: str, source: str) -> dict[str, tuple[str, bool]]:
    found = symbols_in(path, source)
    assert found is not None
    return {s.name: (s.kind, s.public) for s in found}


def test_python_lists_classes_functions_and_methods_and_hides_the_underscored() -> None:
    assert listed("a.py", PY) == {
        "A": ("class", True),
        "A.m": ("method", True),
        "A._p": ("method", False),
        "f": ("function", True),
        "g": ("function", True),
    }


def test_go_lists_types_functions_and_methods_by_receiver_and_public_is_the_capital() -> None:
    assert listed("a.go", GO) == {
        "T": ("type", True),
        "T.M": ("method", True),
        "F": ("function", True),
        "f": ("function", False),
        "I": ("type", True),
    }


def test_java_public_is_the_modifier_and_interface_members_are_public() -> None:
    assert listed("A.java", JAVA) == {
        "A": ("class", True),
        "A.m": ("method", True),
        "A.n": ("method", False),
        "A.I": ("interface", True),
        "A.I.x": ("method", True),
        "A.R": ("record", False),
        "A.E": ("enum", False),
    }


def test_csharp_lists_properties_and_structs_and_public_is_the_modifier() -> None:
    assert listed("A.cs", CS) == {
        "A": ("class", True),
        "A.M": ("method", True),
        "A.N": ("method", False),
        "A.Prop": ("property", True),
        "I": ("interface", True),
        "I.X": ("method", True),
        "S": ("struct", False),
    }


def test_javascript_counts_a_variable_only_when_its_value_is_a_function() -> None:
    assert listed("a.js", JS) == {
        "f": ("function", True),
        "g": ("function", True),
        "A": ("class", False),
        "A.m": ("method", False),
        "h": ("function", False),
    }


def test_typescript_public_is_exported_and_not_private() -> None:
    assert listed("a.ts", TS) == {
        "f": ("function", True),
        "A": ("class", True),
        "A.m": ("method", True),
        "A.p": ("method", False),
        "I": ("interface", True),
        "T": ("type", True),
        "E": ("enum", False),
    }


@pytest.mark.parametrize("path", ["notes.txt", "README.md", "data.json"])
def test_a_file_in_a_language_that_is_not_read_has_no_answer(path: str) -> None:
    assert symbols_in(path, "anything") is None


def test_text_that_does_not_parse_has_no_answer_and_is_never_taken_for_empty() -> None:
    assert symbols_in("a.py", "def (:\n") is None


def test_a_container_changes_only_when_its_header_does() -> None:
    before = symbols_in("a.py", "class A:\n    def m(self): return 1\n")
    after = symbols_in("a.py", "class A:\n    def m(self): return 2\n")
    assert before is not None
    assert after is not None
    assert before[0].shape == after[0].shape
    assert before[1].shape != after[1].shape
    renamed = symbols_in("a.py", "class A(Base):\n    def m(self): return 1\n")
    assert renamed is not None
    assert renamed[0].shape != before[0].shape
