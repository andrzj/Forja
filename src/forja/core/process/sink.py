from collections.abc import Mapping
from typing import Protocol

from forja.core.process.model import ProcessIdentity


class EventSink(Protocol):
    """Where the runner reports. The persisted event log (contract 4) will implement it.

    ``intent`` is called before the process exists and ``effect`` after it ended. ``started``
    carries the identity needed to find a leftover process after a crash, so the log must
    persist it. ``progress`` is display-only and ignored when resuming.
    """

    def intent(self, operation_id: str, details: Mapping[str, object]) -> None: ...

    def started(self, operation_id: str, identity: ProcessIdentity) -> None: ...

    def progress(self, operation_id: str, channel: str, line: str) -> None: ...

    def effect(self, operation_id: str, details: Mapping[str, object]) -> None: ...
