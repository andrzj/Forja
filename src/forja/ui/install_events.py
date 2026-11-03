"""What the installer tells the screen, and the view of the installation kept from it.

The installer only emits these events; it draws nothing. ``InstallModel`` folds them into an
``InstallView``, and every renderer (the full screen, the live line, plain text) draws from a
snapshot of it, as the run view does, so the three layers cannot disagree. Nothing here depends on
a terminal, a network or a file.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum


class Stage(StrEnum):
    WAITING = "waiting"
    DOWNLOADING = "downloading"
    CHECKSUM = "checksum"
    EXTRACTING = "extracting"
    VERIFYING = "verifying"
    READY = "ready"
    PRESENT = "present"
    FAILED = "failed"


ACTIVE = (Stage.DOWNLOADING, Stage.CHECKSUM, Stage.EXTRACTING, Stage.VERIFYING)
SETTLED = (Stage.READY, Stage.PRESENT, Stage.FAILED)


@dataclass(frozen=True)
class ToolInfo:
    """One tool the installer is going to deal with. ``size`` is in bytes."""

    key: str
    name: str
    purpose: str
    version: str
    origin: str
    size: int


@dataclass(frozen=True)
class InstallStarted:
    """The list of tools, in the order they will be handled, and the folder they go to."""

    tools: tuple[ToolInfo, ...]
    destination: str


@dataclass(frozen=True)
class StageEntered:
    """A tool moved to a stage. ``received`` is the bytes downloaded so far (downloading only)."""

    key: str
    stage: Stage
    received: int = 0


@dataclass(frozen=True)
class ToolFailed:
    """A tool did not install: why, and what the person can do about it."""

    key: str
    reason: str
    fix: str = ""


@dataclass(frozen=True)
class InstallFinished:
    pass


InstallEvent = InstallStarted | StageEntered | ToolFailed | InstallFinished


@dataclass(frozen=True)
class ToolRow:
    info: ToolInfo
    stage: Stage = Stage.WAITING
    received: int = 0
    reason: str = ""
    fix: str = ""

    @property
    def active(self) -> bool:
        return self.stage in ACTIVE

    @property
    def progress(self) -> float:
        """How much of this tool is done, from 0 to 1 (a failed one keeps where it stopped)."""
        if self.stage in (Stage.WAITING, Stage.FAILED, Stage.DOWNLOADING):
            if not self.info.size:
                return 0.0
            return min(1.0, self.received / self.info.size)
        return 1.0


@dataclass(frozen=True)
class InstallSummary:
    installed: tuple[ToolRow, ...]
    present: tuple[ToolRow, ...]
    failed: tuple[ToolRow, ...]
    pending: tuple[ToolRow, ...]
    destination: str
    elapsed: float


@dataclass(frozen=True)
class InstallView:
    tools: tuple[ToolRow, ...] = ()
    destination: str = ""
    started: bool = False
    finished: bool = False
    elapsed: float = 0.0

    @property
    def focus(self) -> ToolRow | None:
        """The tool the screen speaks of: the one at work, else a failure, else the next."""
        for wanted in (
            lambda row: row.active,
            lambda row: row.stage is Stage.FAILED,
            lambda row: row.stage is Stage.WAITING,
        ):
            found = next((row for row in self.tools if wanted(row)), None)
            if found:
                return found
        return None

    @property
    def settled(self) -> int:
        return sum(row.stage in SETTLED for row in self.tools)

    @property
    def fraction(self) -> float:
        """The whole installation, by bytes to download (tools already there weigh nothing)."""
        if not self.tools:
            return 0.0
        weighed = [row for row in self.tools if row.stage is not Stage.PRESENT]
        total = sum(row.info.size for row in weighed)
        if not total:
            return self.settled / len(self.tools)
        return sum(row.progress * row.info.size for row in weighed) / total

    @property
    def summary(self) -> InstallSummary:
        def of(*stages: Stage) -> tuple[ToolRow, ...]:
            return tuple(row for row in self.tools if row.stage in stages)

        return InstallSummary(
            installed=of(Stage.READY),
            present=of(Stage.PRESENT),
            failed=of(Stage.FAILED),
            pending=of(Stage.WAITING, *ACTIVE),
            destination=self.destination,
            elapsed=self.elapsed,
        )


@dataclass
class InstallModel:
    """Folds the events of the installer into views. An event that makes no sense is an error."""

    clock: Callable[[], float] = time.monotonic
    _rows: dict[str, ToolRow] = field(default_factory=dict)
    _destination: str = ""
    _begun: float | None = None
    _ended: float | None = None

    def apply(self, event: InstallEvent) -> None:
        if isinstance(event, InstallStarted):
            self._start(event)
        elif self._begun is None:
            raise ValueError("the installation has not started")
        elif isinstance(event, StageEntered):
            self._enter(event)
        elif isinstance(event, ToolFailed):
            row = self._row(event.key)
            self._rows[event.key] = ToolRow(
                row.info, Stage.FAILED, row.received, event.reason, event.fix
            )
        else:
            self._ended = self.clock()

    def _start(self, event: InstallStarted) -> None:
        keys = [tool.key for tool in event.tools]
        if self._begun is not None or len(set(keys)) != len(keys):
            raise ValueError("the installation starts once, with each tool once")
        self._rows = {tool.key: ToolRow(tool) for tool in event.tools}
        self._destination = event.destination
        self._begun = self.clock()

    def _enter(self, event: StageEntered) -> None:
        if event.stage is Stage.FAILED:
            raise ValueError("a failure is told with ToolFailed, which carries the reason")
        row = self._row(event.key)
        received = event.received if event.stage is Stage.DOWNLOADING else row.received
        self._rows[event.key] = ToolRow(row.info, event.stage, max(0, received))

    def _row(self, key: str) -> ToolRow:
        if key not in self._rows:
            raise ValueError(f"unknown tool: {key}")
        return self._rows[key]

    def snapshot(self) -> InstallView:
        if self._begun is None:
            return InstallView()
        end = self._ended if self._ended is not None else self.clock()
        return InstallView(
            tools=tuple(self._rows.values()),
            destination=self._destination,
            started=True,
            finished=self._ended is not None,
            elapsed=end - self._begun,
        )
