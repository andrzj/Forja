"""The conformance check passes on good adapters and catches each way an adapter can go wrong."""

from pathlib import Path

import pytest

from forja.core.adapters import (
    CommandPlan,
    DiscoverySpec,
    LanguageCapability,
    NotSupported,
    Operation,
    OperationRequest,
    ProbeTask,
    TemplateExecutorAdapter,
    ToolOutput,
)
from forja.core.artifacts.models import Producer
from tests.core.adapters.conformance import executor_problems, language_problems
from tests.core.adapters.fakes import FULL_CAPABILITIES, FakeExecutorAdapter, FakeLanguageAdapter

C = LanguageCapability


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    root.mkdir()
    (root / "pyproject.toml").write_text("[project]\nname = 'x'\n")
    return root


def check_language(adapter: FakeLanguageAdapter, project: Path, tmp_path: Path) -> list[str]:
    return language_problems(adapter, project, tmp_path / "scratch")


# -- adapters that are right -------------------------------------------------------------------


def test_the_fake_language_adapter_conforms(project: Path, tmp_path: Path) -> None:
    assert check_language(FakeLanguageAdapter(), project, tmp_path) == []


def test_an_adapter_with_fewer_capabilities_conforms_when_it_is_honest_about_them(
    project: Path, tmp_path: Path
) -> None:
    class Plain(FakeLanguageAdapter):
        capabilities = frozenset({C.PROGRESS_REALTIME})

    assert check_language(Plain(), project, tmp_path) == []


def test_the_fake_agent_conforms(tmp_path: Path) -> None:
    assert executor_problems(FakeExecutorAdapter(), tmp_path / "scratch") == []


def test_a_template_adapter_conforms(tmp_path: Path) -> None:
    adapter = TemplateExecutorAdapter(
        "generic",
        DiscoverySpec(("generic-agent",)),
        ("{executable}", "run", "--role", "{role}", "--file", "{package}"),
        ProbeTask("p", "hello.txt", "hello", frozenset({"TextActivity"})),
    )

    assert executor_problems(adapter, tmp_path / "scratch") == []


def test_a_template_adapter_that_pipes_the_package_conforms(tmp_path: Path) -> None:
    adapter = TemplateExecutorAdapter(
        "piped",
        DiscoverySpec(("piped-agent",)),
        ("{executable}", "--stdin"),
        ProbeTask("p", "hello.txt", "hello", frozenset()),
        package_via_stdin=True,
    )

    assert executor_problems(adapter, tmp_path / "scratch") == []


# -- adapters that are wrong: each mistake is caught -------------------------------------------


def expect(problems: list[str], *fragments: str) -> None:
    for fragment in fragments:
        assert any(fragment in problem for problem in problems), (fragment, problems)


def test_a_claimed_capability_that_cannot_be_planned_is_caught(
    project: Path, tmp_path: Path
) -> None:
    class Liar(FakeLanguageAdapter):
        capabilities = FULL_CAPABILITIES | {C.E2E}

    expect(check_language(Liar(), project, tmp_path), "declares e2e but e2e cannot be planned")


def test_an_operation_planned_without_its_capability_is_caught(
    project: Path, tmp_path: Path
) -> None:
    class Quiet(FakeLanguageAdapter):
        capabilities = FULL_CAPABILITIES - {C.COVERAGE}

        def plan(self, operation, request):  # type: ignore[no-untyped-def]
            return (
                CommandPlan(("fake-cov",), request.root)
                if operation is Operation.COVERAGE
                else super().plan(operation, request)
            )

    expect(check_language(Quiet(), project, tmp_path), "plans coverage without declaring coverage")


def test_an_adapter_that_does_not_say_what_its_coverage_writes_is_caught(
    project: Path, tmp_path: Path
) -> None:
    class Mute(FakeLanguageAdapter):
        report = None  # type: ignore[assignment]

    expect(
        check_language(Mute(), project, tmp_path),
        "declares coverage but has no report()",
    )


def test_a_declared_capability_with_no_report_description_is_caught(
    project: Path, tmp_path: Path
) -> None:
    class Vague(FakeLanguageAdapter):
        def report(self, operation):  # type: ignore[no-untyped-def]
            return NotSupported(operation.value)

    expect(
        check_language(Vague(), project, tmp_path),
        "report(coverage) must describe the report of a declared capability",
    )


def test_a_missing_required_operation_is_caught(project: Path, tmp_path: Path) -> None:
    class NoBuild(FakeLanguageAdapter):
        def plan(self, operation, request):  # type: ignore[no-untyped-def]
            if operation is Operation.BUILD:
                return NotSupported("build")
            return super().plan(operation, request)

    expect(check_language(NoBuild(), project, tmp_path), "build is required but not supported")


def test_a_filter_that_changes_nothing_is_caught(project: Path, tmp_path: Path) -> None:
    class Ignores(FakeLanguageAdapter):
        def plan(self, operation, request):  # type: ignore[no-untyped-def]
            return super().plan(operation, OperationRequest(root=request.root))

    expect(check_language(Ignores(), project, tmp_path), "the filter does not change the command")


def test_ignoring_an_unsupported_filter_instead_of_refusing_it_is_caught(
    project: Path, tmp_path: Path
) -> None:
    class Silent(FakeLanguageAdapter):
        capabilities = frozenset({C.PROGRESS_REALTIME})

        def plan(self, operation, request):  # type: ignore[no-untyped-def]
            return super().plan(operation, OperationRequest(root=request.root))

    expect(
        check_language(Silent(), project, tmp_path),
        "without test_filter_by_file a filtered request must be NotSupported",
        "without test_filter_by_test a filtered request must be NotSupported",
    )


def test_ignoring_incremental_mutation_instead_of_refusing_it_is_caught(
    project: Path, tmp_path: Path
) -> None:
    class NotIncremental(FakeLanguageAdapter):
        capabilities = FULL_CAPABILITIES - {C.MUTATION_INCREMENTAL}

        def plan(self, operation, request):  # type: ignore[no-untyped-def]
            return super().plan(operation, OperationRequest(root=request.root))

    expect(
        check_language(NotIncremental(), project, tmp_path),
        "without mutation_incremental an incremental request must be NotSupported",
    )


def test_a_shell_command_is_caught(project: Path, tmp_path: Path) -> None:
    class Shelly(FakeLanguageAdapter):
        def plan(self, operation, request):  # type: ignore[no-untyped-def]
            if operation is Operation.BUILD:
                return CommandPlan(("bash", "-c", "make && make test"), request.root)
            return super().plan(operation, request)

    expect(check_language(Shelly(), project, tmp_path), "runs through a shell (bash)")


def test_an_unsafe_command_is_caught(project: Path, tmp_path: Path) -> None:
    class Huge(FakeLanguageAdapter):
        def plan(self, operation, request):  # type: ignore[no-untyped-def]
            if operation is Operation.BUILD:
                return CommandPlan(("make", "x" * 9000), request.root)
            return super().plan(operation, request)

    expect(check_language(Huge(), project, tmp_path), "unsafe command")


def test_a_parser_that_crashes_on_odd_output_is_caught(project: Path, tmp_path: Path) -> None:
    class Naive(FakeLanguageAdapter):
        def parse(self, operation, output):  # type: ignore[no-untyped-def]
            line = output.log_path.read_text().splitlines()[0]  # fails on empty and missing logs
            return (
                super().parse(operation, ToolOutput(output.exit_code, output.log_path))
                if line
                else super().parse(operation, output)
            )

    expect(check_language(Naive(), project, tmp_path), "raised")


def test_a_parser_that_is_not_deterministic_is_caught(project: Path, tmp_path: Path) -> None:
    # a stateful adapter: the second answer for the same input differs
    class Flip(FakeLanguageAdapter):
        flag = False

        def classify(self, path):  # type: ignore[no-untyped-def]
            Flip.flag = not Flip.flag
            return None if Flip.flag else super().classify("src/a.py")

    expect(check_language(Flip(), project, tmp_path), "classify is not deterministic")


def test_a_classifier_that_crashes_or_depends_on_the_separator_is_caught(
    project: Path, tmp_path: Path
) -> None:
    class Crashy(FakeLanguageAdapter):
        def classify(self, path):  # type: ignore[no-untyped-def]
            return super().classify(path.split("/")[1])  # IndexError on a bare name

    class Picky(FakeLanguageAdapter):
        def classify(self, path):  # type: ignore[no-untyped-def]
            return super().classify(path) if "\\" not in path else None

    expect(check_language(Crashy(), project, tmp_path), "classify raised")
    expect(check_language(Picky(), project, tmp_path), "treats 'tests/test_a.py' and")


def test_progress_without_the_capability_or_not_a_real_fraction_is_caught(
    project: Path, tmp_path: Path
) -> None:
    class Undeclared(FakeLanguageAdapter):
        capabilities = FULL_CAPABILITIES - {C.PROGRESS_REALTIME}

        def progress_parser(self, operation):  # type: ignore[no-untyped-def]
            return FakeLanguageAdapter().progress_parser(operation)

    class Invented:
        def feed(self, line: str):  # type: ignore[no-untyped-def]
            from forja.core.adapters import Progress

            return Progress(5, 3) if line == "[5/3]" else None

    class Bogus(FakeLanguageAdapter):
        def progress_parser(self, operation):  # type: ignore[no-untyped-def]
            return Invented()

    expect(check_language(Undeclared(), project, tmp_path), "without progress_realtime")
    expect(check_language(Bogus(), project, tmp_path), "5/3 is not a measured fraction")


def test_an_unsupported_language_or_a_detector_that_always_finds_something_is_caught(
    project: Path, tmp_path: Path
) -> None:
    class Cobol(FakeLanguageAdapter):
        language = "cobol"

    class Eager(FakeLanguageAdapter):
        def detect(self, root):  # type: ignore[no-untyped-def]
            return FakeLanguageAdapter().detect(project)

    expect(check_language(Cobol(), project, tmp_path), "not a supported language")
    expect(check_language(Eager(), project, tmp_path), "detect must answer None")


# -- executors that are wrong ------------------------------------------------------------------


def test_a_package_in_the_arguments_is_caught(tmp_path: Path) -> None:
    class Inline(FakeExecutorAdapter):
        def plan_invocation(self, request, setup, executable):  # type: ignore[no-untyped-def]
            return CommandPlan(
                (str(executable), "--prompt", request.package.read_text()), request.workdir
            )

    problems = executor_problems(Inline(), tmp_path / "scratch")

    expect(problems, "puts the package in an argument", "unsafe command")


def test_forgetting_to_deliver_the_package_or_the_working_directory_is_caught(
    tmp_path: Path,
) -> None:
    class Forgetful(FakeExecutorAdapter):
        def plan_invocation(self, request, setup, executable):  # type: ignore[no-untyped-def]
            return CommandPlan((str(executable), "run"), tmp_path)

    expect(
        executor_problems(Forgetful(), tmp_path / "scratch"),
        "does not deliver the package",
        "does not run in the working copy",
    )


def test_an_event_parser_that_crashes_is_caught(tmp_path: Path) -> None:
    class Brittle(FakeExecutorAdapter):
        def parse_event(self, line):  # type: ignore[no-untyped-def]
            import json

            return super().parse_event(line) if json.loads(line) else None

    expect(executor_problems(Brittle(), tmp_path / "scratch"), "parse_event raised")


def test_a_nameless_executor_with_a_bad_probe_is_caught(tmp_path: Path) -> None:
    class Bare(FakeExecutorAdapter):
        name = ""
        env_allow = frozenset({"A=B"})
        probe = ProbeTask("p", "", "", frozenset())

    expect(
        executor_problems(Bare(), tmp_path / "scratch"),
        "has no name",
        "invalid variable name",
        "must expect a file and its content",
    )


def test_the_roles_checked_are_all_agent_roles(tmp_path: Path) -> None:
    seen: set[Producer] = set()

    class Spy(FakeExecutorAdapter):
        def permission_setup(self, role, permissions):  # type: ignore[no-untyped-def]
            seen.add(role)
            return super().permission_setup(role, permissions)

    executor_problems(Spy(), tmp_path / "scratch")

    assert seen == set(Producer) - {Producer.FORJA}
