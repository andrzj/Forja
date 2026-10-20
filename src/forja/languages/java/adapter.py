"""The Java adapter: Maven for build and tests, Spotless (google-java-format) for format,
Checkstyle, PMD and SpotBugs for lint, and JaCoCo for coverage.

It only describes commands and reads their output; the core runs them. Forja installs none of
these: a formatter or linter runs only when the project's ``pom.xml`` declares its plugin, and
without it the operation is not supported (the ``doctor`` and the summary say so). JaCoCo is
different: its goals are named in full, so a project needs nothing for it. Every goal starts with
``clean`` so the reports a tool writes under ``target`` are the ones of this very run. Gradle is
not offered yet.
"""

import re
from pathlib import Path

from forja.core.adapters import (
    CONTRACT_VERSION,
    CommandPlan,
    Detection,
    FileClass,
    LanguageCapability,
    NotSupported,
    Operation,
    OperationRequest,
    ParseResult,
    ProgressParser,
    ToolInfo,
    ToolOutput,
    Unparseable,
    VersionProbe,
)
from forja.core.adapters.executor import locate_in_path
from forja.core.reports import ReportFormat, ReportSpec
from forja.languages.java import parsers

MANIFEST = "pom.xml"
CONFIG_FILES = (
    MANIFEST,
    "checkstyle.xml",
    "pmd-ruleset.xml",
    "spotbugs-exclude.xml",
    ".mvn/maven.config",
    ".mvn/jvm.config",
    ".mvn/extensions.xml",
)
JACOCO = "org.jacoco:jacoco-maven-plugin:0.8.13"
COVERAGE_REPORT = "target/site/jacoco/jacoco.xml"
SOURCE_ROOTS = ("src/main/java",)
_MAVEN_VERSION = r"Apache Maven (\d+\.\d+\.\d+\S*)"
# What Maven and the JDK read from the environment beyond the generic list: where Java is, the
# user's repository of downloaded plugins and the settings of the user's installation.
JAVA_ENVIRONMENT = frozenset(
    {
        "JAVA_HOME",
        "MAVEN_HOME",
        "M2_HOME",
        "MAVEN_OPTS",
        "MAVEN_ARGS",
        "USERPROFILE",
        "HOME",
        "APPDATA",
        "LOCALAPPDATA",
        "ProgramData",
        "ProgramFiles",
    }
)
_BASE = ("-B", "-ntp")
_NO_FAILURE = (
    "-Dcheckstyle.failOnViolation=false",
    "-Dpmd.failOnViolation=false",
    "-Dspotbugs.failOnError=false",
)
_TEST_SUFFIXES = ("Test", "Tests", "IT", "TestCase")
_SKIPPED_DIRECTORIES = frozenset({"target", "build", ".mvn", ".gradle"})


def find_maven() -> tuple[str, ...]:
    """Maven as the platform would start it: on Windows the launcher is ``mvn.cmd``, and a process
    cannot be started from the bare name ``mvn``."""
    found = locate_in_path("mvn")
    return (str(found),) if found else ("mvn",)


def _pom(root: Path) -> str | None:
    try:
        return (root / MANIFEST).read_text(encoding="utf-8")
    except OSError:
        return None


class JavaAdapter:
    contract_version = CONTRACT_VERSION
    language = "java"
    grammar = "java"
    capabilities = frozenset({LanguageCapability.COVERAGE, LanguageCapability.STRUCTURAL_METERS})
    lint_config_files = ("pom.xml",)

    def __init__(self, *, maven: tuple[str, ...] | None = None) -> None:
        self._maven = maven or find_maven()

    # -- finding and classifying ---------------------------------------------------------------

    def detect(self, root: Path) -> Detection | None:
        if not (root / MANIFEST).is_file():
            return None
        probe = VersionProbe(self._plan(root, (*self._maven, "-v")), _MAVEN_VERSION)
        return Detection("java", (".",), (MANIFEST,), probe)

    def classify(self, path: str) -> FileClass | None:
        parts = path.replace("\\", "/").split("/")
        name, directories = parts[-1], parts[:-1]
        if not name.endswith(".java") or _SKIPPED_DIRECTORIES & set(directories):
            return None
        stem = name.removesuffix(".java")
        in_tests = ("src", "test") in zip(directories, directories[1:], strict=False)
        if in_tests or stem.endswith(_TEST_SUFFIXES) or stem.startswith("Test"):
            return FileClass.TEST
        return FileClass.PRODUCTION

    # -- commands ----------------------------------------------------------------------------

    def tool_info(self, operation: Operation) -> ToolInfo | NotSupported:
        maven = VersionProbe(self._plan(Path("."), (*self._maven, "-v")), _MAVEN_VERSION)
        match operation:
            case Operation.FORMAT:
                return ToolInfo("spotless", maven, "maven", maven)
            case Operation.LINT:
                return ToolInfo("checkstyle, pmd, spotbugs", maven, "maven", maven)
            case Operation.BUILD | Operation.TEST:
                return ToolInfo("maven", maven, "maven", maven)
            case Operation.COVERAGE:
                return ToolInfo("jacoco", maven, "maven", maven)
        return NotSupported(operation.value, "the Java adapter does not offer it")

    def plan(self, operation: Operation, request: OperationRequest) -> CommandPlan | NotSupported:
        pom = _pom(request.root)
        if pom is None:
            return NotSupported(operation.value, "the root has no pom.xml")
        mvn = (*self._maven, *_BASE)
        match operation:
            case Operation.FORMAT if "spotless-maven-plugin" in pom:
                if len(request.files) > 1 and self._through_cmd():
                    return NotSupported(
                        operation.value, "cmd.exe would misread the pattern for several files"
                    )
                goal = "spotless:check" if request.check_only else "spotless:apply"
                argv = (*mvn, goal, *self._only(request.files))
            case Operation.LINT if self._linters(pom):
                argv = (*mvn, "clean", "compile", *self._linters(pom), *_NO_FAILURE)
            case Operation.BUILD:
                argv = (*mvn, "clean", "test-compile")
            case Operation.TEST | Operation.COVERAGE if request.tests or request.test_files:
                return NotSupported(operation.value, "filtering the tests is not offered")
            case Operation.TEST:
                argv = (*mvn, "clean", "test")
            case Operation.COVERAGE:
                argv = (
                    *mvn,
                    "clean",
                    f"{JACOCO}:prepare-agent",
                    "test",
                    f"{JACOCO}:report",
                )
            case Operation.FORMAT | Operation.LINT:
                return NotSupported(operation.value, "the project does not declare that tool")
            case _:
                return NotSupported(operation.value, "the Java adapter does not offer it")
        return self._plan(request.root, argv, config_files=CONFIG_FILES)

    def _through_cmd(self) -> bool:
        return Path(self._maven[0]).suffix.lower() in {".cmd", ".bat"}

    @staticmethod
    def _linters(pom: str) -> tuple[str, ...]:
        goals = (
            ("maven-checkstyle-plugin", "checkstyle:check"),
            ("maven-pmd-plugin", "pmd:check"),
            ("spotbugs-maven-plugin", "spotbugs:check"),
        )
        return tuple(goal for plugin, goal in goals if plugin in pom)

    @staticmethod
    def _only(files: tuple[str, ...]) -> tuple[str, ...]:
        """Spotless takes a regular expression that is matched against the whole path."""
        if not files:
            return ()
        names = "|".join(
            re.escape(name.replace("\\", "/")).replace("/", "[/\\\\]") for name in files
        )
        return (f"-DspotlessFiles=.*[/\\\\]({names})",)

    def report(self, operation: Operation) -> ReportSpec | NotSupported:
        if operation is Operation.COVERAGE:
            return ReportSpec(ReportFormat.JACOCO_XML, COVERAGE_REPORT, SOURCE_ROOTS)
        return NotSupported(operation.value, "the Java adapter writes no such report")

    @staticmethod
    def _plan(root: Path, argv: tuple[str, ...], config_files: tuple[str, ...] = ()) -> CommandPlan:
        return CommandPlan(
            argv,
            root,
            env_allow=JAVA_ENVIRONMENT,
            env_set={"NO_COLOR": "1"},
            config_files=config_files,
        )

    # -- reading what they print ---------------------------------------------------------------

    def parse(self, operation: Operation, output: ToolOutput) -> ParseResult:
        match operation:
            case Operation.FORMAT:
                return parsers.parse_format(output)
            case Operation.LINT:
                return parsers.parse_lint(output)
            case Operation.BUILD:
                return parsers.parse_build(output)
            case Operation.TEST:
                return parsers.parse_tests(output)
        return Unparseable(f"the Java adapter does not read {operation.value} output")

    def progress_parser(self, operation: Operation) -> ProgressParser | None:
        return None
