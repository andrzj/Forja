"""The packages each language's manifests declare, and the refusal to read what cannot be read."""

from typing import Any

import pytest

from forja.checks.new_dependency import Declared, manifests_of
from forja.languages import (
    CSharpAdapter,
    GoAdapter,
    JavaAdapter,
    PythonAdapter,
    TypeScriptAdapter,
)
from forja.languages.csharp.manifest import declared_dependencies as csharp
from forja.languages.go.manifest import declared_dependencies as go
from forja.languages.java.manifest import declared_dependencies as java
from forja.languages.python.manifest import declared_dependencies as python
from forja.languages.typescript.manifest import declared_dependencies as typescript

PYPROJECT = """
[project]
name = "x"
dependencies = ["requests>=2", "Flask[async] ; python_version > '3.8'"]
[project.optional-dependencies]
docs = ["sphinx"]
[dependency-groups]
dev = ["pytest", {include-group = "docs"}]
"""


def test_python_reads_pyproject_in_all_three_places_and_skips_group_includes() -> None:
    assert python("sub/pyproject.toml", PYPROJECT) == frozenset(
        {"requests", "Flask", "sphinx", "pytest"}
    )


def test_python_reads_requirements_and_skips_options_urls_and_paths() -> None:
    text = "# c\nrequests==2.0  # pinned\n-r base.txt\n--index-url https://x\n./local\ngit+https://g/x\n\nnumpy\n"

    assert python("requirements-dev.txt", text) == frozenset({"requests", "numpy"})
    assert python("requirements.txt", "") == frozenset()


def test_python_ignores_other_files_and_refuses_broken_toml() -> None:
    assert python("setup.py", "x") is None
    assert python("notes/requirements.md", "x") is None
    with pytest.raises(ValueError, match="TOML"):
        python("pyproject.toml", "[project")


def test_typescript_reads_the_four_sections_and_only_what_comes_from_the_registry() -> None:
    text = """{"dependencies": {"a": "^1", "b": "file:../b", "c": "user/repo", "d": "npm:real@2",
      "e": "workspace:*", "f": "git+https://x", "@s/g": "1.0.0"},
      "devDependencies": {"h": "*"}, "optionalDependencies": {"i": "1"},
      "peerDependencies": {"j": ">=1"}}"""

    assert typescript("web/package.json", text) == frozenset({"a", "real", "@s/g", "h", "i", "j"})


def test_typescript_ignores_other_files_and_refuses_what_is_not_json() -> None:
    assert typescript("package-lock.json", "{}") is None
    with pytest.raises(ValueError, match="JSON"):
        typescript("package.json", "{")
    with pytest.raises(ValueError, match="object"):
        typescript("package.json", "[]")


def test_go_reads_single_lines_and_blocks_and_ignores_replace_and_comments() -> None:
    text = """module m
go 1.22
require example.com/a v1.0.0
require (
\texample.com/b v1.2.3 // indirect
\t// example.com/zzz v1.0.0
\tgithub.com/BurntSushi/toml v1.0.0
)
replace example.com/b => ../b
exclude example.com/c v1.0.0
"""

    assert go("svc/go.mod", text) == frozenset(
        {
            "example.com/a",
            "example.com/b",
            "github.com/BurntSushi/toml",
        }
    )
    assert go("go.sum", "x") is None


def test_java_reads_pom_dependencies_and_skips_properties() -> None:
    text = """<project xmlns="http://maven.apache.org/POM/4.0.0"><dependencies>
      <dependency><groupId>com.google.inject</groupId><artifactId>guice</artifactId></dependency>
      <dependency><groupId>${g}</groupId><artifactId>x</artifactId></dependency>
    </dependencies></project>"""

    assert java("pom.xml", text) == frozenset({"com.google.inject:guice"})


def test_java_reads_gradle_string_notation_only() -> None:
    text = """dependencies {
    implementation("org.slf4j:slf4j-api:2.0.9")
    testImplementation 'junit:junit:4.13'
    api(libs.guava)
    implementation project(":core")
}
"""

    assert java("app/build.gradle.kts", text) == frozenset({"org.slf4j:slf4j-api", "junit:junit"})
    assert java("build.gradle", text) == frozenset({"org.slf4j:slf4j-api", "junit:junit"})


@pytest.mark.parametrize(
    "text",
    [
        '<!DOCTYPE x [<!ENTITY a "aaaa">]><project/>',
        "<!doctype x><project/>",
        "<project><!ENTITY a 'b'></project>",
        "<project",
    ],
)
def test_xml_manifests_with_entities_or_broken_markup_are_refused(text: str) -> None:
    with pytest.raises(ValueError):
        java("pom.xml", text)
    with pytest.raises(ValueError):
        csharp("a.csproj", text)


def test_csharp_reads_package_references_in_projects_props_and_packages_config() -> None:
    project = (
        '<Project Sdk="Microsoft.NET.Sdk"><ItemGroup>'
        '<PackageReference Include="Serilog" Version="3" />'
        '<PackageReference Include="$(Dynamic)" />'
        '<PackageReference Update="X" /></ItemGroup></Project>'
    )
    props = '<Project><ItemGroup><PackageVersion Include="Moq" Version="4" /></ItemGroup></Project>'
    config = '<packages><package id="Old.Thing" version="1" /></packages>'

    assert csharp("src/App.csproj", project) == frozenset({"Serilog"})
    assert csharp("Directory.Packages.props", props) == frozenset({"Moq"})
    assert csharp("packages.config", config) == frozenset({"Old.Thing"})
    assert csharp("App.cs", "class A {}") is None
    assert csharp("App.csproj", config) == frozenset()  # ``package`` only counts in packages.config


def test_the_adapters_declare_their_registry_and_the_composition_picks_the_one_that_reads() -> None:
    adapters: list[Any] = [
        PythonAdapter(),
        GoAdapter(),
        TypeScriptAdapter(),
        JavaAdapter(),
        CSharpAdapter(),
    ]
    declared = manifests_of(adapters)

    assert [a.dependency_ecosystem for a in adapters] == ["PyPI", "Go", "npm", "Maven", "NuGet"]
    assert declared("go.mod", "require a.b/c v1.0.0\n") == Declared(
        "go", "Go", frozenset({"a.b/c"})
    )
    assert declared("package.json", '{"dependencies": {"a": "1"}}') == Declared(
        "typescript", "npm", frozenset({"a"})
    )
    assert declared("README.md", "x") is None
    with pytest.raises(ValueError):
        declared("package.json", "{")


def test_the_registry_may_hold_adapters_that_cannot_read_manifests() -> None:
    class Bare:
        language = "bare"

    assert manifests_of([Bare()])("go.mod", "") is None


@pytest.mark.parametrize(
    "text",
    [
        "require(\n\texample.com/a v1.0.0\n)\n",
        "require\t(\n\texample.com/a v1.0.0\n)\n",
        "require\texample.com/a v1.0.0\n",
        "require (example.com/a v1.0.0)\n",
        'require (\n\t"example.com/a" v1.0.0\n)\n',
        "require (\n\texample.com/a v1.0.0 )\n",
        "require example.com/a v1.0.0 // indirect\n",
    ],
)
def test_go_reads_requirements_the_way_go_tokenizes_them(text: str) -> None:
    assert go("go.mod", text) == frozenset({"example.com/a"})


def test_go_keeps_reading_after_a_block_and_ignores_an_empty_one() -> None:
    text = "require ()\nrequire (\n)\nrequire example.com/b v1.0.0\n"

    assert go("go.mod", text) == frozenset({"example.com/b"})


def test_python_names_do_not_keep_the_space_before_them() -> None:
    text = '[project]\ndependencies = ["  spaced>=1", "\ttabbed"]\n'

    assert python("pyproject.toml", text) == frozenset({"spaced", "tabbed"})


def test_python_requirement_comments_are_cut_before_looking_for_a_url() -> None:
    text = "numpy  # docs: https://numpy.org\nscipy @ https://x.dev/scipy.whl\n"

    assert python("requirements.txt", text) == frozenset({"numpy"})


def test_python_options_comments_blanks_and_paths_name_nothing() -> None:
    text = "-r base.txt\n--index-url x\n# c\n\n./local\n/abs\n"

    assert python("requirements.txt", text) == frozenset()


@pytest.mark.parametrize(
    ("spec", "expected"),
    [("npm:@s/real", "@s/real"), ("npm:a@1", "a"), ("npm:@s/real@2", "@s/real"), ("npm:b", "b")],
)
def test_typescript_aliases_name_the_package_they_point_to(spec: str, expected: str) -> None:
    text = '{"dependencies": {"alias": "' + spec + '"}}'

    assert typescript("package.json", text) == frozenset({expected})


@pytest.mark.parametrize(
    "text", ["<!DOCTYPE x><project/>", "<project><!ENTITY a 'b'></project>", "<!doctype x><a/>"]
)
def test_the_refusal_of_entities_says_so_and_a_broken_document_says_that(text: str) -> None:
    with pytest.raises(ValueError, match="DOCTYPE or entity"):
        java("pom.xml", text)
    with pytest.raises(ValueError, match="not valid XML"):
        java("pom.xml", "<project")
