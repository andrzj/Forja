"""Gate 9: an attempt must not make a directory depend on a layer above its own.

The layers are the ones the repository declares, from the top down; Forja never deduces them. A
layer may depend on itself and on the ones below. Only an edge the attempt added reproves: a
dependency that already pointed upward is the repository's past. Directories in no layer are free.
"""

import asyncio
from dataclasses import dataclass

from forja.checks.architecture.compare import Compared, Snapshot, compare
from forja.checks.base import rejected
from forja.core.gates import Approved, Finding, GateInput, GateResult, NotApplicable
from forja.core.policy import ArchitectureLayer

NO_LAYERS = "architecture_layers"


@dataclass(frozen=True)
class LayerRulesCheck:
    before: Snapshot  # the parent commit
    after: Snapshot  # the attempt
    changed: tuple[str, ...]  # production files the attempt added, changed or renamed
    layers: tuple[ArchitectureLayer, ...]  # top to bottom
    base: str = ""  # where the project sits in the repository; layers are repository paths
    id: str = "layer_rules"
    gate: int = 9
    requires: frozenset[str] = frozenset({"structural_meters"})

    async def evaluate(self, data: GateInput) -> GateResult:
        if not self.layers:
            return NotApplicable(missing_capability=NO_LAYERS)
        return await asyncio.to_thread(self._judge)

    def _judge(self) -> GateResult:
        found = compare(self.before, self.after, self.changed)
        if not isinstance(found, Compared):
            return found
        old = found.before.edges if found.before is not None else frozenset()
        findings = []
        for importer, imported in sorted(found.after.edges - old):
            low, high = self._layer_of(importer), self._layer_of(imported)
            if low is None or high is None or high >= low:
                continue
            message = (
                f"layer {self.layers[low].name} depends on {self.layers[high].name}, "
                "a layer above it"
            )
            findings.append(Finding(message=message, target=f"{importer} -> {imported}"))
        return rejected(findings) if findings else Approved()

    def _layer_of(self, folder: str) -> int | None:
        """The position of the layer that holds ``folder``: the one with the deepest path."""
        path = self.base if folder == "." else f"{self.base}/{folder}".lstrip("/")
        best: tuple[int, int] | None = None  # (path length, position)
        for position, layer in enumerate(self.layers):
            for held in layer.paths:
                inside = path == held or path.startswith(held + "/")
                if inside and (best is None or len(held) > best[0]):
                    best = (len(held), position)
        return None if best is None else best[1]
