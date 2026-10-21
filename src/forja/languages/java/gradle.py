"""Gradle as the build tool of the Java adapter: the commands, as seen in real runs of Gradle 9.8.2.

Nothing is applied to the project except JaCoCo, which an init script names in full (as the Maven
goals do). A linter or the formatter runs only when the build file declares its plugin. The init
scripts are data next to this module (``init_scripts``): they make the linters not fail the build
and make SpotBugs and JaCoCo write XML. Tasks are matched by name there because the plugin classes
do not resolve in an init script.
"""

import re
import sys
from pathlib import Path

from forja.core.adapters.executor import locate_in_path

MANIFESTS = ("build.gradle", "build.gradle.kts")
CONFIG_FILES = (
    *MANIFESTS,
    "settings.gradle",
    "settings.gradle.kts",
    "gradle.properties",
    "gradle/libs.versions.toml",
    "gradle/wrapper/gradle-wrapper.properties",
    "config/checkstyle/checkstyle.xml",
    "config/pmd/ruleSet.xml",
)
VERSION = r"Gradle (\d+\.\d+(?:\.\d+)?\S*)"
COVERAGE_REPORT = "build/reports/jacoco/test/jacocoTestReport.xml"
ENVIRONMENT = frozenset({"GRADLE_USER_HOME", "GRADLE_OPTS", "GRADLE_HOME"})
_SCRIPTS = Path(__file__).parent / "init_scripts"
_BASE = ("--console", "plain")


def manifest(root: Path) -> str | None:
    """The text of the build file at the root, or ``None`` if there is none."""
    for name in MANIFESTS:
        try:
            return (root / name).read_text(encoding="utf-8")
        except OSError:
            continue
    return None


def find_gradle(root: Path) -> tuple[str, ...]:
    """The wrapper the repository carries, else ``gradle`` as the platform would start it."""
    wrapper = root / ("gradlew.bat" if sys.platform == "win32" else "gradlew")
    if wrapper.is_file():
        return (str(wrapper),)
    found = locate_in_path("gradle")
    return (str(found),) if found else ("gradle",)


def _script(name: str) -> tuple[str, str]:
    return ("-I", str(_SCRIPTS / f"{name}.init.gradle"))


def linter_tasks(build: str) -> tuple[str, ...]:
    tasks = (
        ("checkstyle", "checkstyleMain"),
        ("pmd", "pmdMain"),
        ("com.github.spotbugs", "spotbugsMain"),
    )
    return tuple(task for plugin, task in tasks if re.search(rf"\b{re.escape(plugin)}\b", build))


def declares_spotless(build: str) -> bool:
    return "com.diffplug.spotless" in build


def build_argv(gradle: tuple[str, ...]) -> tuple[str, ...]:
    return (*gradle, *_BASE, "compileJava", "compileTestJava")


def test_argv(gradle: tuple[str, ...]) -> tuple[str, ...]:
    return (*gradle, *_BASE, "cleanTest", "test")


def coverage_argv(gradle: tuple[str, ...]) -> tuple[str, ...]:
    """``--continue``: ``jacocoTestReport`` does not run if ``test`` fails."""
    return (
        *gradle,
        *_BASE,
        "--continue",
        *_script("coverage"),
        "cleanTest",
        "test",
        "jacocoTestReport",
    )


def lint_argv(gradle: tuple[str, ...], tasks: tuple[str, ...]) -> tuple[str, ...]:
    return (*gradle, *_BASE, "--continue", *_script("lint"), *_script("spotbugs"), *tasks)


def format_argv(
    gradle: tuple[str, ...], root: Path, files: tuple[str, ...], check_only: bool
) -> tuple[str, ...]:
    """One file goes through Spotless' IDE hook; anything else, the whole project."""
    task = "spotlessCheck" if check_only else "spotlessApply"
    if len(files) == 1:
        return (*gradle, *_BASE, f"-PspotlessIdeHook={root / files[0]}", task)
    return (*gradle, *_BASE, task)
