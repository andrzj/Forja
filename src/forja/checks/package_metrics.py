"""Gate 9: an attempt must not push a directory away from the main sequence of Martin's metrics.

A directory sits well when it is either stable and abstract or unstable and concrete; its distance
``D`` from that line is ``|A + I - 1|``. Only a directory the attempt touched reproves, and only
when its ``D`` is over the limit and grew, or the directory is new. A directory with few types
says too little about itself and is left alone.
"""

import asyncio
from dataclasses import dataclass

from forja.checks.architecture.compare import Compared, Snapshot, compare
from forja.checks.base import rejected
from forja.checks.shape import threshold
from forja.core.gates import Approved, Finding, GateInput, GateResult

DEFAULT_MAX_DISTANCE = 0.8  # a guess; the owner dropped the calibration
DEFAULT_MIN_TYPES = 3


@dataclass(frozen=True)
class PackageMetricsCheck:
    before: Snapshot  # the parent commit
    after: Snapshot  # the attempt
    changed: tuple[str, ...]  # production files the attempt added, changed or renamed
    id: str = "package_metrics"
    gate: int = 9
    requires: frozenset[str] = frozenset({"structural_meters"})

    async def evaluate(self, data: GateInput) -> GateResult:
        return await asyncio.to_thread(self._judge, data)

    def _judge(self, data: GateInput) -> GateResult:
        found = compare(self.before, self.after, self.changed)
        if not isinstance(found, Compared):
            return found
        language = self.after.language
        limit = threshold(data, language, "max_distance", DEFAULT_MAX_DISTANCE)
        least = threshold(data, language, "min_types", DEFAULT_MIN_TYPES)
        findings = []
        for folder in sorted(found.touched & found.after.nodes):
            now = found.after.metrics(folder)
            if now.types < least or now.distance <= limit:
                continue
            old = found.before
            if (
                old is not None
                and folder in old.nodes
                and now.distance <= old.metrics(folder).distance
            ):
                continue
            findings.append(
                Finding(
                    message="package is far from the main sequence",
                    target=folder,
                    measured=round(now.distance, 2),
                    limit=limit,
                )
            )
        return rejected(findings) if findings else Approved()
