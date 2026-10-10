class TransientFailure(Exception):
    """A problem that waiting or retrying may fix, such as a busy lock or a file in use.

    The orchestrator treats it as an infrastructure failure: it never counts as an attempt of
    the task, and repeating it pauses the run instead of failing the task.
    """
