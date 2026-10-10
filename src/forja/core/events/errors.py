class EventLogError(Exception):
    """Base for every problem with the event log."""


class CorruptLogError(EventLogError):
    """A line in the middle of the log is damaged or breaks the rules; resuming is refused."""

    def __init__(self, line: int, reason: str) -> None:
        self.line = line
        self.reason = reason
        super().__init__(f"event log is corrupt at line {line}: {reason}")


class UnsupportedSchemaVersion(EventLogError):
    """The log was written by a newer Forja; reading it could silently misread it."""

    def __init__(self, version: int, supported: int) -> None:
        self.version = version
        super().__init__(
            f"event schema version {version} is newer than the supported version {supported}; "
            "upgrade Forja to resume this run"
        )


class InvalidEvent(EventLogError):
    """The event breaks the rules of the run (unknown target, wrong origin, bad parent...)."""


class LogUnusable(EventLogError):
    """An earlier write failed, so the file may end in a partial line. Reopen the log."""
