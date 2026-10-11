"""What the checks share: asking an adapter for a command, running it, and reading the output."""

from collections.abc import Awaitable, Mapping

from pydantic import JsonValue

from forja.checks.tooling import Tools
from forja.core.adapters import (
    CommandPlan,
    LanguageAdapter,
    NotSupported,
    Operation,
    OperationRequest,
    Parsed,
    Unparseable,
    plan_with_override,
)
from forja.core.gates import (
    Finding,
    GateResult,
    Inconclusive,
    InconclusiveReason,
    NotApplicable,
    Rejected,
)

MAX_FINDINGS = 20  # the next attempt is told the worst of it, not a wall of text


def overrides_from(
    adapter: LanguageAdapter, values: Mapping[str, JsonValue]
) -> dict[str, dict[str, tuple[str, ...]]]:
    """The repository's own commands, from the policy values of one check."""
    commands = values.get("commands")
    if not isinstance(commands, dict):
        return {}
    found = {
        name: tuple(str(part) for part in argv)
        for name, argv in commands.items()
        if isinstance(argv, list) and argv
    }
    return {adapter.language: found} if found else {}


class Undecided(Exception):
    """The measurement could not be made; ``result`` is what the check answers instead."""

    def __init__(self, result: Inconclusive | NotApplicable) -> None:
        self.result = result
        super().__init__(result.result)


async def decided(judgment: Awaitable[GateResult]) -> GateResult:
    """Run a check's judgment, turning a measurement that could not be made into its result."""
    try:
        return await judgment
    except Undecided as stop:
        return stop.result


async def measure(
    tools: Tools,
    adapter: LanguageAdapter,
    operation: Operation,
    name: str,
    request: OperationRequest,
    overrides: Mapping[str, Mapping[str, tuple[str, ...]]] | None = None,
) -> Parsed:
    """Plan, run and read one operation, or raise ``Undecided``."""
    plan = plan_with_override(adapter, operation, request, overrides or {})
    if isinstance(plan, NotSupported):
        raise Undecided(NotApplicable(missing_capability=operation.value))
    return await measure_plan(tools, adapter, operation, name, plan)


async def measure_plan(
    tools: Tools, adapter: LanguageAdapter, operation: Operation, name: str, plan: CommandPlan
) -> Parsed:
    execution = await tools.run(name, plan)
    if not execution.finished:
        raise Undecided(execution.inconclusive(name))
    parsed = adapter.parse(operation, execution.output)
    if isinstance(parsed, Unparseable):
        raise Undecided(
            Inconclusive(
                reason=InconclusiveReason.TOOL_FAILED,
                detail=f"{name}: {parsed.reason}",
                tool_run_ids=(execution.operation_id,),
            )
        )
    return parsed


def rejected(findings: list[Finding]) -> Rejected:
    return Rejected(findings=tuple(findings[:MAX_FINDINGS]))
