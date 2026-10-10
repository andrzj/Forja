import dataclasses
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum

from pydantic import JsonValue

from forja.core.gates.check import Check, GateInput
from forja.core.gates.effects import STOPPING_EFFECTS, CheckSettings, decide_effect
from forja.core.gates.models import Effect, GateResult, NotApplicable


class Verdict(StrEnum):
    PASSED = "passed"
    REJECTED = "rejected"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class CheckRun:
    check_id: str
    gate: int
    settings: CheckSettings
    result: GateResult
    effect: Effect


@dataclass(frozen=True)
class PipelineOutcome:
    runs: tuple[CheckRun, ...]

    @property
    def stopped_by(self) -> CheckRun | None:
        """The check that ended the sequence, if any; later checks did not run."""
        return next((run for run in self.runs if run.effect in STOPPING_EFFECTS), None)

    @property
    def verdict(self) -> Verdict:
        stopper = self.stopped_by
        if stopper is None:
            return Verdict.PASSED
        return Verdict.REJECTED if stopper.effect is Effect.REJECT_ATTEMPT else Verdict.BLOCKED

    @property
    def assumptions(self) -> tuple[CheckRun, ...]:
        """Gaps the run continued through; each becomes a declared assumption in the PR."""
        return tuple(r for r in self.runs if r.effect is Effect.CONTINUE_WITH_ASSUMPTION)

    @property
    def reports(self) -> tuple[CheckRun, ...]:
        """Results that only go to the PR: observation findings and checks that did not apply."""
        return tuple(
            r
            for r in self.runs
            if r.effect is Effect.REPORT_ONLY or isinstance(r.result, NotApplicable)
        )


class GatePipeline:
    """Runs the checks in gate order and stops at the first one that must stop the sequence.

    A check runs only if the ones before it did not reject the attempt or block the task. Checks
    in observation mode never stop anything, so the ones after them still run. A crash inside a
    check is a bug in Forja and propagates instead of being turned into a result.
    """

    def __init__(
        self,
        checks: Sequence[Check],
        settings: Mapping[str, CheckSettings],
        values: Mapping[str, Mapping[str, JsonValue]] | None = None,
    ) -> None:
        ids = [check.id for check in checks]
        if len(ids) != len(set(ids)):
            raise ValueError("check ids must be unique")
        missing = [i for i in ids if i not in settings]
        if missing:
            raise ValueError(f"checks without settings: {sorted(missing)}")
        for check in checks:
            if check.gate < 1:
                raise ValueError(f"check {check.id!r}: gate numbers start at 1")
        self._checks = sorted(
            checks, key=lambda check: check.gate
        )  # stable: keeps registration order
        self._settings = settings
        self._values = values or {}

    async def run(self, data: GateInput, capabilities: Collection[str]) -> PipelineOutcome:
        available = set(capabilities)
        runs: list[CheckRun] = []
        for check in self._checks:
            settings = self._settings[check.id]
            absent = sorted(check.requires - available)
            result: GateResult
            if absent:
                result = NotApplicable(missing_capability=absent[0])
            else:
                scoped = dataclasses.replace(data, values=self._values.get(check.id, {}))
                result = await check.evaluate(scoped)
            run = CheckRun(check.id, check.gate, settings, result, decide_effect(settings, result))
            runs.append(run)
            if run.effect in STOPPING_EFFECTS:
                break
        return PipelineOutcome(tuple(runs))
