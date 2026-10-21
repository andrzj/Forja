"""A test id that carries no path belongs to a file only if the file says the test's name."""

from typing import Any

import pytest

from forja.languages.csharp import CSharpAdapter
from forja.languages.go import GoAdapter
from forja.languages.java import JavaAdapter
from forja.languages.typescript import TypeScriptAdapter

GO = "func TestAdd(t *testing.T) {}\nfunc TestAddAll(t *testing.T) {}\n"
JAVA = "class AddTest { @Test void adds() {} }"
CSHARP = "public class AddTests { [Fact] public void Adds() {} }"


@pytest.mark.parametrize(
    ("adapter", "test_id", "path", "text", "owned"),
    [
        (GoAdapter(), "example.com/calc/TestAdd", "a_test.go", GO, True),
        (GoAdapter(), "example.com/calc/TestAdd/sub_case", "a_test.go", GO, True),
        (GoAdapter(), "example.com/calc/TestOther", "a_test.go", GO, False),
        (GoAdapter(), "example.com/calc/TestAddAl", "a_test.go", GO, False),
        (GoAdapter(), "example.com/calc", "a_test.go", GO, False),
        (JavaAdapter(), "com.acme.AddTest.adds", "AddTest.java", JAVA, True),
        (JavaAdapter(), "com.acme.AddTest.adds[1]", "AddTest.java", JAVA, True),
        (JavaAdapter(), "com.acme.AddTest.subtracts", "AddTest.java", JAVA, False),
        (JavaAdapter(), "com.acme.OtherTest.adds", "AddTest.java", JAVA, False),
        (JavaAdapter(), "adds", "AddTest.java", JAVA, False),
        (CSharpAdapter(), "Calc.Tests.AddTests.Adds", "AddTests.cs", CSHARP, True),
        (CSharpAdapter(), "Calc.Tests.AddTests.Adds(a: 1)", "AddTests.cs", CSHARP, True),
        (CSharpAdapter(), "Calc.Tests.AddTests.Subtracts", "AddTests.cs", CSHARP, False),
        (CSharpAdapter(), "Calc.Tests.OtherTests.Adds", "AddTests.cs", CSHARP, False),
        (TypeScriptAdapter(), "add.test.ts > adds", "add.test.ts", "", True),
        (TypeScriptAdapter(), "add.test.ts", "add.test.ts", "", True),
        (TypeScriptAdapter(), "add.test.ts > s > adds", "pkg/add.test.ts", "", True),
        (TypeScriptAdapter(), "other.test.ts > adds", "add.test.ts", "", False),
        (TypeScriptAdapter(), "adds", "add.test.ts", "", False),
    ],
)
def test_an_id_without_a_path_belongs_to_the_file_that_says_its_name(
    adapter: Any, test_id: str, path: str, text: str, owned: bool
) -> None:
    assert adapter.owns_test(test_id, path, text) is owned
