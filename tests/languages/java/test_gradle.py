"""The Java adapter on a Gradle project: what it detects and the commands it plans."""

import sys
from pathlib import Path

import pytest

from forja.core.adapters import (
    CommandPlan,
    NotSupported,
    Operation,
    OperationRequest,
    ToolInfo,
)
from forja.core.reports import ReportFormat
from forja.languages.java import JavaAdapter, gradle

GRADLE = ("g",)
ADAPTER = JavaAdapter(maven=("m",), gradle=GRADLE)
PLUGINS = """plugins {
    id 'java'
    id 'checkstyle'
    id 'pmd'
    id 'com.github.spotbugs' version '6.0.26'
    id 'com.diffplug.spotless' version '7.0.2'
}
"""


def project(root: Path, build: str = PLUGINS, name: str = "build.gradle") -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / name).write_text(build, encoding="utf-8")
    return root


def planned(root: Path, operation: Operation, **request: object) -> CommandPlan:
    result = ADAPTER.plan(operation, OperationRequest(root=root, **request))  # type: ignore[arg-type]
    assert isinstance(result, CommandPlan), result
    return result


def test_a_build_file_makes_it_a_gradle_project(tmp_path: Path) -> None:
    found = ADAPTER.detect(project(tmp_path, name="build.gradle.kts"))
    assert found is not None
    assert found.manifests == ("build.gradle.kts",)
    assert found.toolchain_probe is not None
    assert found.toolchain_probe.plan.argv == (*GRADLE, "-v")
    assert found.toolchain_probe.pattern == gradle.VERSION


def test_a_pom_wins_over_a_build_file(tmp_path: Path) -> None:
    project(tmp_path)
    (tmp_path / "pom.xml").write_text("<project/>", encoding="utf-8")
    found = ADAPTER.detect(tmp_path)
    assert found is not None
    assert found.manifests == ("pom.xml",)
    assert planned(tmp_path, Operation.BUILD).argv[0] == "m"


def test_neither_manifest_is_not_java(tmp_path: Path) -> None:
    assert ADAPTER.detect(tmp_path) is None
    assert isinstance(ADAPTER.plan(Operation.BUILD, OperationRequest(root=tmp_path)), NotSupported)


def test_the_wrapper_of_the_repository_is_used_before_the_path(tmp_path: Path) -> None:
    assert gradle.find_gradle(tmp_path)[0].lower().endswith(("gradle", "gradle.bat", "gradle.exe"))
    wrapper = tmp_path / ("gradlew.bat" if sys.platform == "win32" else "gradlew")
    wrapper.write_text("", encoding="utf-8")
    assert gradle.find_gradle(tmp_path) == (str(wrapper),)


def test_build_and_test(tmp_path: Path) -> None:
    root = project(tmp_path)
    assert planned(root, Operation.BUILD).argv == (
        "g", "--console", "plain", "compileJava", "compileTestJava"
    )  # fmt: skip
    plan = planned(root, Operation.TEST)
    assert plan.argv == ("g", "--console", "plain", "cleanTest", "test")
    assert plan.cwd == root
    assert plan.config_files == gradle.CONFIG_FILES
    assert {"JAVA_HOME", "GRADLE_USER_HOME"} <= plan.env_allow


def test_coverage_continues_past_failing_tests_and_names_jacoco_in_an_init_script(
    tmp_path: Path,
) -> None:
    argv = planned(project(tmp_path), Operation.COVERAGE).argv
    assert "--continue" in argv
    assert argv[-3:] == ("cleanTest", "test", "jacocoTestReport")
    script = Path(argv[argv.index("-I") + 1])
    assert script.is_file()
    assert "jacoco" in script.read_text(encoding="utf-8")


def test_lint_runs_the_declared_linters_only(tmp_path: Path) -> None:
    argv = planned(project(tmp_path), Operation.LINT).argv
    assert argv[-3:] == ("checkstyleMain", "pmdMain", "spotbugsMain")
    only = planned(project(tmp_path / "b", "plugins { id 'checkstyle' }"), Operation.LINT).argv
    assert only[-1] == "checkstyleMain"
    assert "pmdMain" not in only
    scripts = [Path(only[i + 1]).name for i, part in enumerate(only) if part == "-I"]
    assert scripts == ["lint.init.gradle", "spotbugs.init.gradle"]


def test_a_plugin_name_inside_another_word_is_not_the_plugin(tmp_path: Path) -> None:
    root = project(tmp_path, "// not a linter: pmdx, mycheckstyles\n")
    assert isinstance(ADAPTER.plan(Operation.LINT, OperationRequest(root=root)), NotSupported)


@pytest.mark.parametrize("operation", [Operation.FORMAT, Operation.LINT])
def test_an_undeclared_tool_is_not_supported(tmp_path: Path, operation: Operation) -> None:
    result = ADAPTER.plan(operation, OperationRequest(root=project(tmp_path, "plugins {}")))
    assert isinstance(result, NotSupported)
    assert "does not declare" in result.reason


def test_format_one_file_goes_through_the_ide_hook(tmp_path: Path) -> None:
    root = project(tmp_path)
    check = planned(root, Operation.FORMAT, files=("src/main/java/A.java",), check_only=True)
    assert check.argv[-2:] == (
        f"-PspotlessIdeHook={root / 'src/main/java/A.java'}",
        "spotlessCheck",
    )
    apply = planned(root, Operation.FORMAT, files=("src/main/java/A.java",), check_only=False)
    assert apply.argv[-1] == "spotlessApply"


@pytest.mark.parametrize("files", [(), ("A.java", "B.java")])
def test_format_none_or_several_files_goes_through_the_project(
    tmp_path: Path, files: tuple[str, ...]
) -> None:
    argv = planned(project(tmp_path), Operation.FORMAT, files=files, check_only=True).argv
    assert argv == ("g", "--console", "plain", "spotlessCheck")


@pytest.mark.parametrize("operation", [Operation.TEST, Operation.COVERAGE])
def test_filtering_tests_is_not_offered(tmp_path: Path, operation: Operation) -> None:
    result = ADAPTER.plan(operation, OperationRequest(root=project(tmp_path), tests=("a.B.c",)))
    assert isinstance(result, NotSupported)


def test_what_it_reports_follows_the_build_tool(tmp_path: Path) -> None:
    adapter = JavaAdapter(maven=("m",), gradle=GRADLE)
    adapter.detect(project(tmp_path))
    spec = adapter.report(Operation.COVERAGE)
    assert not isinstance(spec, NotSupported)
    assert spec.format is ReportFormat.JACOCO_XML
    assert spec.path == gradle.COVERAGE_REPORT
    info = adapter.tool_info(Operation.TEST)
    assert isinstance(info, ToolInfo)
    assert info.tool == "gradle"
    assert info.tool_probe.pattern == gradle.VERSION
