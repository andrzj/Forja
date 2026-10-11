"""Runs the scenario in this process, for a test that kills it where the environment says to."""

import os
import sys
from pathlib import Path

from tests.orchestrator.crash import (
    PAUSE_ENV,
    stall_from_environment,
    torn_write_from_environment,
)
from tests.orchestrator.fakes import ContentMeasurer, ScriptedAgent
from tests.orchestrator.harness import World
from tests.orchestrator.resume_support import scenario


def main() -> None:
    root = Path(sys.argv[1])
    world = World.at(root)
    log = world.open(write=torn_write_from_environment(root))
    agent = ScriptedAgent(
        in_process=False, by_feedback=True, pause=float(os.environ.get(PAUSE_ENV, "0"))
    )
    scenario(
        world, log=log, agent=agent, measurer=ContentMeasurer(), hook=stall_from_environment(root)
    )
    log.close()


if __name__ == "__main__":
    main()
