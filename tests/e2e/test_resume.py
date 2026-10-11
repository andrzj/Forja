"""A run interrupted at any boundary resumes and ends where an uninterrupted run ends.

Contract 2 and 4 together: the log is the only memory, and the idempotency table says what to do
with the operation that was in flight. See ``driver.py`` for the scripted run.
"""

from typing import Any

import pytest

from forja.core.events import LogUnusable
from tests.e2e.driver import CrashAfter, Interrupted
from tests.e2e.support import (
    TOTAL_LINES,
    assert_same_end,
    open_operations,
    restart,
    run_until_it_ends,
)
from tests.e2e.world import World

# Cuts just before an intent or an effect: the lines where a half-written event matters most.
TORN_CUTS = (
    7, 8, 12, 13, 14, 15, 18, 21, 23, 24, 25, 26, 28, 29, 31, 32,
    33, 34, 37, 40, 42, 43, 44, 45, 47, 48, 51, 52, 53, 54,
)  # fmt: skip

pytestmark = pytest.mark.slow


def test_an_uninterrupted_run_delivers_what_the_script_promises(
    reference: dict[str, Any],
) -> None:
    fp = reference["fingerprint"]

    assert (fp["execution"], fp["task"], fp["stage"]) == ("delivered", "integrated", "committed")
    assert fp["attempts"] == {"rejected": 1, "committed": 1}
    assert fp["open_operations"] == [] and fp["infra_failures"] == 0
    assert fp["worktrees"] == 1  # only the repository itself is left
    assert len(fp["evidence"]) == 2 and len(fp["blobs"]) == 1


def test_the_script_is_cut_at_every_line_it_writes(reference: dict[str, Any]) -> None:
    assert reference["lines"] == TOTAL_LINES


def test_lines_torn_in_half_are_tried_at_every_start_and_end_of_an_operation(
    reference: dict[str, Any],
) -> None:
    boundaries = {n - 1 for n, kind, _ in reference["marks"] if kind in ("intent", "effect")}

    assert boundaries == set(TORN_CUTS)


CASES = [(cut, False) for cut in range(TOTAL_LINES + 1)] + [(cut, True) for cut in TORN_CUTS]


@pytest.mark.parametrize(
    ("cut", "torn"), CASES, ids=[f"{cut}-{'torn' if torn else 'clean'}" for cut, torn in CASES]
)
def test_interrupted_after_the_nth_line_the_run_resumes_to_the_same_end(
    world: World, reference: dict[str, Any], cut: int, torn: bool
) -> None:
    try:
        run_until_it_ends(world, write=CrashAfter(cut, torn=torn))
    except (Interrupted, LogUnusable):
        pass  # the runner may report the dead log instead of the failed write itself
    else:
        assert cut == TOTAL_LINES, "the run ended before the cut"
    open_at_crash = open_operations(world)

    plan = restart(world)

    assert_same_end(world, reference["fingerprint"], plan, open_at_crash)
    assert len(list(world.run_dir.glob("events.jsonl.discarded-*"))) == int(torn)
