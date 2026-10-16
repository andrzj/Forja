"""Working adapters made of fixed answers, for tests of everything that uses adapters."""

import json
import re
from pathlib import Path

from forja.core.adapters import (
    AGENT_DIR,
    CONTRACT_VERSION,
    AgentActivity,
    AgentRequest,
    CommandActivity,
    CommandPlan,
    Detection,
    DiscoverySpec,
    ErrorActivity,
    ErrorKind,
    EvidenceDraft,
    FileClass,
    FileEditActivity,
    FileReadActivity,
    LanguageCapability,
    NotSupported,
    Operation,
    OperationRequest,
    Parsed,
    ParseResult,
    PermissionSetup,
    ProbeTask,
    Progress,
    ProgressParser,
    RolePermissions,
    TextActivity,
    ToolInfo,
    ToolOutput,
    Unparseable,
    UsageActivity,
    VersionProbe,
    read_output_lines,
)
from forja.core.artifacts.models import Producer
from forja.core.evidence import Target, TargetKind
from forja.core.reports import ReportFormat, ReportSpec

C = LanguageCapability
FULL_CAPABILITIES = frozenset(
    {
        C.TEST_FILTER_BY_FILE,
        C.TEST_FILTER_BY_TEST,
        C.COVERAGE,
        C.MUTATION,
        C.MUTATION_INCREMENTAL,
        C.PROGRESS_REALTIME,
        C.STRUCTURAL_METERS,
    }
)
_COUNT = re.compile(r"^RESULT passed=(\d{1,9}) failed=(\d{1,9})$")
_COVERAGE = re.compile(r"^COVERAGE (\d{1,3}(?:\.\d{1,4})?)$")
_PROGRESS = re.compile(r"^\[(\d{1,9})/(\d{1,9})\]")
_SUPPORTED = {
    Operation.FORMAT,
    Operation.LINT,
    Operation.LINT_FIX,
    Operation.BUILD,
    Operation.TEST,
    Operation.COVERAGE,
    Operation.MUTATION,
}


class _CountingProgress:
    def feed(self, line: str) -> Progress | None:
        match = _PROGRESS.match(line)
        if not match:
            return None
        done, total = int(match.group(1)), int(match.group(2))
        return Progress(done, total, "tests") if 0 <= done <= total and total > 0 else None


class FakeLanguageAdapter:
    """A tidy Python-like adapter that does everything the interface allows."""

    contract_version = CONTRACT_VERSION
    language = "python"
    grammar: str | None = "python"
    capabilities: frozenset[LanguageCapability] = FULL_CAPABILITIES

    def detect(self, root: Path) -> Detection | None:
        if not (root / "pyproject.toml").is_file():
            return None
        probe = VersionProbe(CommandPlan(("python", "--version"), root), r"Python (\d+\.\d+\.\d+)")
        return Detection("python", (".",), ("pyproject.toml",), probe)

    def classify(self, path: str) -> FileClass | None:
        normal = path.replace("\\", "/")
        name = normal.rsplit("/", 1)[-1]
        if "fixtures/" in normal:
            return FileClass.FIXTURE
        if normal.endswith((".md", ".rst")):
            return FileClass.DOCUMENTATION
        if normal.endswith(".py"):
            is_test = normal.startswith("tests/") or name.startswith("test_")
            return FileClass.TEST if is_test else FileClass.PRODUCTION
        return None

    def tool_info(self, operation: Operation) -> ToolInfo | NotSupported:
        if operation not in _SUPPORTED:
            return NotSupported(operation.value)
        tool = VersionProbe(CommandPlan(("fake-tool", "--version"), Path(".")), r"(\d+\.\d+\.\d+)")
        chain = VersionProbe(CommandPlan(("python", "--version"), Path(".")), r"(\d+\.\d+\.\d+)")
        return ToolInfo("fake-tool", tool, "python", chain)

    def plan(self, operation: Operation, request: OperationRequest) -> CommandPlan | NotSupported:
        if operation not in _SUPPORTED:
            return NotSupported(operation.value, "this adapter has no such operation")
        if request.test_files and C.TEST_FILTER_BY_FILE not in self.capabilities:
            return NotSupported(operation.value, "no filter by file")
        if request.tests and C.TEST_FILTER_BY_TEST not in self.capabilities:
            return NotSupported(operation.value, "no filter by test")
        if request.incremental and C.MUTATION_INCREMENTAL not in self.capabilities:
            return NotSupported(operation.value, "no incremental mutation")
        if operation is Operation.COVERAGE and C.COVERAGE not in self.capabilities:
            return NotSupported(operation.value)
        if operation is Operation.MUTATION and C.MUTATION not in self.capabilities:
            return NotSupported(operation.value)

        argv = [f"fake-{operation.value}"]
        for file in request.test_files:
            argv += ["--file", file]
        for test in request.tests:
            argv += ["--test", test]
        if request.incremental:
            argv += ["--incremental", *request.changed_files]
        return CommandPlan(
            tuple(argv),
            request.root,
            env_set={"NO_COLOR": "1"},
            config_files=("pyproject.toml",),
        )

    def report(self, operation: Operation) -> ReportSpec | NotSupported:
        if operation is Operation.COVERAGE and C.COVERAGE in self.capabilities:
            return ReportSpec(ReportFormat.COVERAGE_PY_JSON, "target/coverage/coverage.json")
        return NotSupported(operation.value)

    def parse(self, operation: Operation, output: ToolOutput) -> ParseResult:
        lines = read_output_lines(output.log_path)
        module = Target(kind=TargetKind.MODULE, id=".")
        if operation is Operation.TEST:
            for line in lines:
                match = _COUNT.match(line)
                if match:
                    return Parsed(
                        (
                            EvidenceDraft("tests_passed", module, int(match.group(1)), "count"),
                            EvidenceDraft("tests_failed", module, int(match.group(2)), "count"),
                        )
                    )
            return Unparseable("no RESULT line in the output")
        if operation is Operation.COVERAGE:
            for line in lines:
                match = _COVERAGE.match(line)
                if match:
                    return Parsed(
                        (EvidenceDraft("line_coverage", module, float(match.group(1)), "percent"),)
                    )
            return Unparseable("no COVERAGE line in the output")
        if output.exit_code == 0:
            return Parsed((EvidenceDraft(f"{operation.value}_ok", module, True, "bool"),))
        return Unparseable(f"{operation.value} exited with {output.exit_code}")

    def progress_parser(self, operation: Operation) -> ProgressParser | None:
        if operation is Operation.TEST and C.PROGRESS_REALTIME in self.capabilities:
            return _CountingProgress()
        return None


class FakeExecutorAdapter:
    """An agent CLI that talks JSON lines and takes its package from a file."""

    contract_version = CONTRACT_VERSION
    name = "fake-agent"
    discovery = DiscoverySpec(
        ("fake-agent",), version_pattern=r"fake-agent (\d+\.\d+\.\d+)", min_version="1.2"
    )
    env_allow = frozenset({"FAKE_API_KEY", "FAKE_BASE_URL"})
    enforces_permissions = True
    probe = ProbeTask(
        "write 'hello' to hello.txt",
        "hello.txt",
        "hello",
        frozenset({"TextActivity", "FileEditActivity"}),
    )

    def permission_setup(self, role: Producer, permissions: RolePermissions) -> PermissionSetup:
        settings = {
            "role": role.value,
            "can_edit_files": permissions.can_edit_files,
            "allowed_commands": list(permissions.allowed_commands),
        }
        return PermissionSetup(
            {"settings.json": json.dumps(settings, sort_keys=True).encode()},
            ("--settings", f"{AGENT_DIR}/settings.json"),
        )

    def plan_invocation(
        self, request: AgentRequest, setup: PermissionSetup, executable: Path
    ) -> CommandPlan:
        argv = (str(executable), "--prompt-file", str(request.package), *setup.extra_args)
        return CommandPlan(argv, request.workdir, env_allow=self.env_allow)

    def parse_event(self, line: str) -> AgentActivity | None:
        try:
            event = json.loads(line)
        except ValueError:
            return None
        if not isinstance(event, dict):
            return None
        kind = event.get("type")
        try:
            if kind == "text" and isinstance(event.get("text"), str):
                return TextActivity(event["text"])
            if kind == "read" and isinstance(event.get("path"), str):
                return FileReadActivity(event["path"])
            if kind == "edit" and isinstance(event.get("path"), str):
                return FileEditActivity(
                    event["path"], _count(event.get("added")), _count(event.get("removed"))
                )
            if kind == "command" and isinstance(event.get("command"), str):
                code = event.get("exit_code")
                return CommandActivity(event["command"], code if isinstance(code, int) else None)
            if kind == "usage":
                return UsageActivity(
                    _optional(event.get("input_tokens")), _optional(event.get("output_tokens"))
                )
            if kind == "error" and isinstance(event.get("message"), str):
                return ErrorActivity(event["message"], ErrorKind(event.get("kind", "persistent")))
        except ValueError:
            return None
        return None


def _count(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0


def _optional(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None
