"""The readers of a file's shape: which functions only pass work on, and how big the surface is."""

import pytest

from forja.checks.structure import SUFFIXES, SyntaxProblem, analyze

PYTHON = """\
class A:
    def f(self, a, b=1, *c, **k):
        '''Docs do not count as a statement of the body.'''
        return self.x.g(a, b, *c, **k)

    def swapped(self, a, b):
        return self.x.g(b, a)

    def more(self, a):
        return self.x.g(a + 1)

    def extra(self, a):
        return self.x.g(a, 1)

    def two(self, a):
        print(a)
        return self.x.g(a)

    @property
    def decorated(self):
        return self.x()

    def __init__(self, a):
        super().__init__(a)


def named(a, b: int):
    g(a, b=b)
"""

GO = """\
package p

func (s *S) F(a int, xs ...int) int {
\treturn s.x.G(a, xs...)
}

func H(a, b int) int { return G(a, b) }

func changed(a int) { G(a + 1) }
"""

JAVA = """\
public class A {
  public A(int a) { this.a = a; }
  public int f(int a, String... b) { return x.g(a, b); }
  public int changed(int a) { return x.g(a + 1); }
  public void other(int a) { x.g(a); x.h(a); }
}
"""

CSHARP = """\
namespace N {
  public class A {
    public int F(int a, int b) { return G(a, b); }
    public int E(int a) => G(a);
    public int R(int a) => G(ref a);
    public int Named(int a) => G(x: a);
  }
}
"""

TYPESCRIPT = """\
export class B {
  f(a: number, ...r: any[]) { return this.x.g(a, ...r); }
  private q(a) { return g(a); }
  constructor(a) { super(a); }
  h(a) { return g(a, 1); }
}
export const k = (a) => g(a);
export function m(a, b) { return g(a, b); }
function plain(a) { return g(a + 1); }
"""

JAVASCRIPT = "export function m(a) { return g(a); }\nfunction n(a) { return g(a + 1); }\n"

CASES = [
    ("a.py", PYTHON, {"A.f", "named"}),
    ("a.go", GO, {"S.F", "H"}),
    ("A.java", JAVA, {"A.f"}),
    ("A.cs", CSHARP, {"A.F", "A.E"}),
    ("a.ts", TYPESCRIPT, {"B.f", "B.q", "k", "m"}),
    ("a.tsx", TYPESCRIPT, {"B.f", "B.q", "k", "m"}),
    ("a.js", JAVASCRIPT, {"m"}),
]


@pytest.mark.parametrize(("path", "source", "expected"), CASES)
def test_only_the_functions_that_pass_their_arguments_on_unchanged_are_found(
    path: str, source: str, expected: set[str]
) -> None:
    module = analyze(path, source)

    assert module is not None
    assert module.forwarders == expected


def test_python_counts_public_names_and_their_parameters_and_the_all_list_wins() -> None:
    source = (
        "def one(a, b):\n    return a\n\n\ndef _hidden(a):\n    return a\n\n\nclass C:\n    pass\n"
    )

    module = analyze("a.py", source)

    assert module is not None
    assert module.interface == 3 + 1  # one(a, b) is 3; the empty class is 1; _hidden is not public
    listed = analyze("a.py", source + "__all__ = ['one']\n")
    assert listed is not None
    assert listed.interface == 3


def test_go_exports_start_with_a_capital_letter() -> None:
    module = analyze("a.go", "package p\n\nfunc Open(a int) {}\n\nfunc close(a int, b int) {}\n")

    assert module is not None
    assert module.interface == 2


def test_java_and_csharp_count_only_public_types_and_members() -> None:
    java = analyze(
        "A.java", "public class A {\n  public void a(int x) {}\n  private void b(int x) {}\n}\n"
    )
    csharp = analyze(
        "A.cs", "public class A {\n  public void A1(int x) {}\n  private void B(int x) {}\n}\n"
    )

    assert java is not None and csharp is not None
    assert java.interface == csharp.interface == 1 + 2


def test_typescript_counts_exported_names_and_skips_private_members() -> None:
    module = analyze(
        "a.ts",
        "export class B { pub(a) {} private hid(a) {} }\nclass Inner { f(a) {} }\n"
        "export interface I { m(a: number): void; x: number }\n",
    )

    assert module is not None
    assert module.interface == (1 + 2) + (1 + 2 + 1)


def test_the_size_of_the_implementation_counts_statements_and_not_imports() -> None:
    module = analyze("a.py", "import os\nfrom x import y\n\n\ndef f():\n    a = 1\n    return a\n")

    assert module is not None
    assert module.statements == 3  # the def, the assignment, the return


def test_a_language_forja_does_not_read_is_left_alone() -> None:
    assert analyze("notes.txt", "def f(:") is None


def test_text_that_does_not_parse_is_a_problem_not_an_empty_module() -> None:
    with pytest.raises(SyntaxProblem):
        analyze("a.py", "def f(:\n")


def test_every_language_of_the_forja_has_a_reader() -> None:
    assert {".py", ".go", ".java", ".cs", ".js", ".ts", ".tsx"} <= set(SUFFIXES)
