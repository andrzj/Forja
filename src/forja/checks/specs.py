"""What the policy may say about each check, and what it says when left alone."""

from forja.core.gates import InconclusivePolicy, Mode
from forja.core.policy.registry import CheckRegistry, CheckSpec

BLOCK = InconclusivePolicy.BLOCK
PREMISE = InconclusivePolicy.PREMISE


def default_registry() -> CheckRegistry:
    """The checks of increment 1. A tool that cannot run blocks the task, except complexity,
    whose gap is declared as an assumption because its limit is not calibrated yet."""
    registry = CheckRegistry()
    for spec in (
        CheckSpec("scope", 1, Mode.BLOCKING, BLOCK, limits=frozenset({"max_files", "max_lines"})),
        CheckSpec("freeze", 1, Mode.BLOCKING, BLOCK),
        CheckSpec("secrets", 2, Mode.BLOCKING, BLOCK),
        CheckSpec("format", 3, Mode.BLOCKING, BLOCK, commands=frozenset({"format"})),
        CheckSpec("lint", 3, Mode.BLOCKING, BLOCK, commands=frozenset({"lint"})),
        CheckSpec("build", 4, Mode.BLOCKING, BLOCK, commands=frozenset({"build"})),
        CheckSpec("tests", 5, Mode.BLOCKING, BLOCK, commands=frozenset({"test"})),
        CheckSpec("red_green", 5, Mode.BLOCKING, BLOCK, commands=frozenset({"test"})),
        CheckSpec(
            "mutation",
            7,
            Mode.OBSERVATION,
            PREMISE,
            thresholds=frozenset({"min_score"}),
            limits=frozenset({"workers"}),
        ),
        CheckSpec("complexity", 8, Mode.BLOCKING, PREMISE, thresholds=frozenset({"max_ccn"})),
        CheckSpec("crap", 8, Mode.OBSERVATION, PREMISE, thresholds=frozenset({"max_crap"})),
    ):
        registry.register(spec)
    return registry
