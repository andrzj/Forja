from enum import StrEnum


class Level(StrEnum):
    """Nesting levels of the run: a run holds tasks, a task holds stages, a stage holds attempts."""

    EXECUTION = "execution"
    TASK = "task"
    STAGE = "stage"
    ATTEMPT = "attempt"
