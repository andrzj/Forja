import uuid


def new_id() -> str:
    """Short opaque id for runs, tasks, stages and attempts.

    12 hex characters keep branch names and Windows worktree paths short.
    """
    return uuid.uuid4().hex[:12]
