"""Installations made by hand: the tools and events of a made-up installer, no network."""

from forja.ui.install_events import (
    InstallEvent,
    InstallFinished,
    InstallModel,
    InstallStarted,
    InstallView,
    Stage,
    StageEntered,
    ToolFailed,
    ToolInfo,
)

MB = 1024 * 1024
HOSTILE = "\x1b]0;pwned\x07\x1b[2J" + "界" * 30 + "‮\u0007tail\n\r\t"

GITLEAKS = ToolInfo(
    "gitleaks", "gitleaks", "procura segredos no código", "8.21.2",
    "github.com/gitleaks/gitleaks", 8 * MB,
)  # fmt: skip
SEMGREP = ToolInfo(
    "semgrep", "semgrep", "análise estática de segurança", "1.95.0", "pypi.org/project/semgrep",
    40 * MB,
)  # fmt: skip
OSV = ToolInfo(
    "osv-scanner", "osv-scanner", "audita dependências conhecidas", "1.9.1",
    "github.com/google/osv-scanner", 12 * MB,
)  # fmt: skip
JSCPD = ToolInfo(
    "jscpd", "jscpd", "acha código duplicado", "4.0.5", "npmjs.com/package/jscpd", 2 * MB
)  # fmt: skip
TOOLS = (GITLEAKS, SEMGREP, OSV, JSCPD)
DESTINATION = "C:\\Users\\ana\\.forja\\ferramentas"


class Clock:
    """A clock that only moves when told to."""

    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


def played(*events: InstallEvent, seconds: float = 35.0) -> InstallView:
    """The view after the events, with ``seconds`` gone since the start (at the end if it runs)."""
    clock = Clock()
    model = InstallModel(clock=clock)
    for event in events:
        if isinstance(event, InstallFinished):
            clock.now += seconds
        model.apply(event)
    if not model.snapshot().finished:
        clock.now += seconds
    return model.snapshot()


def started(tools: tuple[ToolInfo, ...] = TOOLS) -> InstallStarted:
    return InstallStarted(tools, DESTINATION)


def downloading(key: str, received: int) -> StageEntered:
    return StageEntered(key, Stage.DOWNLOADING, received)


def at(key: str, stage: Stage) -> StageEntered:
    return StageEntered(key, stage)


def success() -> list[InstallEvent]:
    """The whole installation going well: one tool already there, three installed."""
    events: list[InstallEvent] = [started(), at("jscpd", Stage.PRESENT)]
    for tool in (GITLEAKS, SEMGREP, OSV):
        events += [
            downloading(tool.key, 0),
            downloading(tool.key, tool.size // 2),
            downloading(tool.key, tool.size),
            at(tool.key, Stage.CHECKSUM),
            at(tool.key, Stage.EXTRACTING),
            at(tool.key, Stage.VERIFYING),
            at(tool.key, Stage.READY),
        ]
    return [*events, InstallFinished()]


def with_failure() -> list[InstallEvent]:
    """The semgrep download fails after a quarter of it; the others go on."""
    events: list[InstallEvent] = [started(), downloading("gitleaks", 8 * MB)]
    events += [at("gitleaks", s) for s in (Stage.CHECKSUM, Stage.EXTRACTING, Stage.VERIFYING)]
    events += [at("gitleaks", Stage.READY), downloading("semgrep", 10 * MB)]
    events += [
        ToolFailed(
            "semgrep", "o servidor pypi.org não respondeu (tempo esgotado)", "confira a rede"
        ),
        at("osv-scanner", Stage.PRESENT),
        ToolFailed("jscpd", "checksum diferente do esperado"),
        InstallFinished(),
    ]
    return events


MID = (started(), downloading("gitleaks", 2 * MB))
VIEWS = {
    "not started": InstallView(),
    "nothing to do": played(InstallStarted((), DESTINATION), InstallFinished()),
    "queued": played(started()),
    "downloading": played(*MID),
    "verifying": played(*MID, at("gitleaks", Stage.VERIFYING)),
    "done": played(*success()),
    "failed": played(*with_failure()),
    "stopped": played(*MID, InstallFinished()),
    "hostile": played(
        InstallStarted((ToolInfo(HOSTILE, HOSTILE, HOSTILE, HOSTILE, HOSTILE, 5 * MB),), HOSTILE),
        ToolFailed(HOSTILE, HOSTILE, HOSTILE),
        InstallFinished(),
    ),
}
