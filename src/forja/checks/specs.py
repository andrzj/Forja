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
        CheckSpec("e2e", 6, Mode.OBSERVATION, BLOCK),
        CheckSpec("test_data", 6, Mode.OBSERVATION, PREMISE),
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
        CheckSpec("pass_through", 8, Mode.OBSERVATION, PREMISE),
        CheckSpec(
            "module_depth",
            8,
            Mode.OBSERVATION,
            PREMISE,
            thresholds=frozenset({"max_interface_ratio", "min_statements"}),
        ),
        CheckSpec("sast", 10, Mode.OBSERVATION, BLOCK),
        CheckSpec("dependency_audit", 10, Mode.OBSERVATION, BLOCK),
        CheckSpec(
            "new_dependency",
            10,
            Mode.OBSERVATION,
            PREMISE,
            thresholds=frozenset({"min_age_days", "min_downloads"}),
        ),
        CheckSpec("citations", 13, Mode.OBSERVATION, BLOCK),
        CheckSpec("change_record", 14, Mode.OBSERVATION, BLOCK),
    ):
        registry.register(spec)
    return registry
