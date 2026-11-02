"""The events of the installer and the view kept from them."""

import pytest

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
    ToolRow,
)
from forja.ui.install_panels import size_text
from tests.ui.install_support import (
    DESTINATION,
    GITLEAKS,
    JSCPD,
    MB,
    OSV,
    SEMGREP,
    TOOLS,
    Clock,
    at,
    downloading,
    played,
    started,
    success,
    with_failure,
)


def test_before_the_start_the_view_is_empty() -> None:
    view = InstallModel().snapshot()
    assert view == InstallView()
    assert not view.started and not view.finished and view.focus is None
    assert view.fraction == 0.0


def test_the_tools_keep_the_order_they_were_announced_in() -> None:
    view = played(started())
    assert [row.info.key for row in view.tools] == ["gitleaks", "semgrep", "osv-scanner", "jscpd"]
    assert all(row.stage is Stage.WAITING for row in view.tools)
    assert view.destination == DESTINATION and view.started and not view.finished


def test_a_tool_moves_through_its_stages_and_remembers_the_download() -> None:
    view = played(started(), downloading("gitleaks", 2 * MB))
    row = view.tools[0]
    assert (row.stage, row.received, row.active) == (Stage.DOWNLOADING, 2 * MB, True)
    assert row.progress == 0.25
    view = played(started(), downloading("gitleaks", 2 * MB), at("gitleaks", Stage.CHECKSUM))
    row = view.tools[0]
    assert (row.stage, row.received, row.active, row.progress) == (
        Stage.CHECKSUM,
        2 * MB,
        True,
        1.0,
    )


def test_received_only_counts_while_downloading_and_never_goes_below_zero() -> None:
    view = played(started(), StageEntered("gitleaks", Stage.EXTRACTING, 999))
    assert view.tools[0].received == 0
    view = played(started(), downloading("gitleaks", -5))
    assert view.tools[0].received == 0


def test_progress_is_capped_and_a_tool_of_no_size_has_none_until_it_is_done() -> None:
    assert ToolRow(GITLEAKS, Stage.DOWNLOADING, 99 * MB).progress == 1.0
    empty = ToolInfo("x", "x", "", "1", "o", 0)
    assert ToolRow(empty, Stage.DOWNLOADING, 5).progress == 0.0
    assert ToolRow(empty, Stage.WAITING).progress == 0.0
    assert ToolRow(empty, Stage.READY).progress == 1.0
    assert ToolRow(GITLEAKS, Stage.WAITING).progress == 0.0
    assert ToolRow(GITLEAKS, Stage.PRESENT).progress == 1.0
    assert ToolRow(GITLEAKS, Stage.FAILED, 2 * MB).progress == 0.25


@pytest.mark.parametrize(
    ("stage", "active"),
    [
        (Stage.WAITING, False),
        (Stage.DOWNLOADING, True),
        (Stage.CHECKSUM, True),
        (Stage.EXTRACTING, True),
        (Stage.VERIFYING, True),
        (Stage.READY, False),
        (Stage.PRESENT, False),
        (Stage.FAILED, False),
    ],
)
def test_which_stages_are_work_in_progress(stage: Stage, active: bool) -> None:
    assert ToolRow(GITLEAKS, stage).active is active


def test_a_failure_keeps_where_the_download_stopped_and_says_why() -> None:
    view = played(
        started(), downloading("semgrep", 10 * MB), ToolFailed("semgrep", "rede", "tente")
    )
    row = view.tools[1]
    assert (row.stage, row.received, row.reason, row.fix) == (
        Stage.FAILED,
        10 * MB,
        "rede",
        "tente",
    )
    assert not row.active


def key_of_focus(view: InstallView) -> str | None:
    return view.focus.info.key if view.focus else None


def test_the_focus_is_the_tool_at_work_then_a_failure_then_the_next_one() -> None:
    assert key_of_focus(played(started())) == "gitleaks"
    mid = played(started(), at("gitleaks", Stage.READY), downloading("semgrep", 1))
    assert key_of_focus(mid) == "semgrep"
    failed = played(
        started(),
        at("gitleaks", Stage.READY),
        ToolFailed("semgrep", "x"),
        at("osv-scanner", Stage.READY),
    )
    assert key_of_focus(failed) == "semgrep"
    assert key_of_focus(played(started(), at("gitleaks", Stage.READY))) == "semgrep"
    assert key_of_focus(played(*success())) is None
    both = played(started(), ToolFailed("gitleaks", "x"), downloading("jscpd", 0))
    assert key_of_focus(both) == "jscpd"


def test_settled_counts_what_is_over_whatever_the_outcome() -> None:
    assert played(*with_failure()).settled == 4
    assert played(started(), at("gitleaks", Stage.VERIFYING)).settled == 0
    assert played(started(), at("gitleaks", Stage.READY)).settled == 1
    assert played(started(), at("gitleaks", Stage.PRESENT)).settled == 1


def test_the_whole_is_weighed_by_bytes_and_tools_already_there_weigh_nothing() -> None:
    assert played(started()).fraction == 0.0
    half = played(started(), at("jscpd", Stage.PRESENT), downloading("semgrep", 20 * MB))
    # gitleaks 8, semgrep 40 and osv 12 are to be downloaded: 20 of 60 MB
    assert half.fraction == pytest.approx(20 / 60)
    assert played(*success()).fraction == 1.0
    two = InstallStarted((GITLEAKS, JSCPD), DESTINATION)
    assert played(two, at("gitleaks", Stage.PRESENT)).fraction == 0.0  # jscpd: 0 of 2 MB
    nothing = InstallStarted((ToolInfo("x", "x", "", "1", "o", 0),), DESTINATION)
    assert played(nothing).fraction == 0.0
    assert played(nothing, at("x", Stage.PRESENT)).fraction == 1.0  # counted by tools
    assert played(nothing, at("x", Stage.READY)).fraction == 1.0


def test_the_summary_sorts_the_tools_by_outcome() -> None:
    report = played(*with_failure()).summary
    assert [row.info.key for row in report.installed] == ["gitleaks"]
    assert [row.info.key for row in report.present] == ["osv-scanner"]
    assert [row.info.key for row in report.failed] == ["semgrep", "jscpd"]
    assert report.pending == ()
    assert report.destination == DESTINATION and report.elapsed == 35.0
    stopped = played(started(), downloading("gitleaks", 1), InstallFinished()).summary
    assert [row.info.key for row in stopped.pending] == [t.key for t in TOOLS]


def test_the_time_runs_until_the_end_and_stops_there() -> None:
    clock = Clock()
    model = InstallModel(clock=clock)
    model.apply(started())
    clock.now += 10
    assert model.snapshot().elapsed == 10 and not model.snapshot().finished
    model.apply(InstallFinished())
    clock.now += 99
    assert model.snapshot().elapsed == 10 and model.snapshot().finished


@pytest.mark.parametrize(
    "event", [InstallFinished(), at("gitleaks", Stage.READY), ToolFailed("gitleaks", "x")]
)
def test_an_event_before_the_start_is_an_error(event: InstallEvent) -> None:
    with pytest.raises(ValueError, match="has not started"):
        InstallModel().apply(event)


@pytest.mark.parametrize("event", [at("nope", Stage.READY), ToolFailed("nope", "x")])
def test_an_unknown_tool_is_an_error(event: InstallEvent) -> None:
    model = InstallModel()
    model.apply(started())
    with pytest.raises(ValueError, match="unknown tool: nope"):
        model.apply(event)


def test_a_failure_is_told_with_its_own_event() -> None:
    model = InstallModel()
    model.apply(started())
    with pytest.raises(ValueError, match="ToolFailed"):
        model.apply(StageEntered("gitleaks", Stage.FAILED))


def test_the_installation_starts_once_and_each_tool_once() -> None:
    model = InstallModel()
    model.apply(started())
    with pytest.raises(ValueError, match="starts once"):
        model.apply(started())
    with pytest.raises(ValueError, match="starts once"):
        InstallModel().apply(InstallStarted((GITLEAKS, GITLEAKS), "d"))


def test_the_tools_of_the_tests_are_what_the_tests_say() -> None:
    assert [tool.key for tool in TOOLS] == ["gitleaks", "semgrep", "osv-scanner", "jscpd"]
    assert (SEMGREP.size, OSV.size, JSCPD.size) == (40 * MB, 12 * MB, 2 * MB)


@pytest.mark.parametrize(
    ("size", "text"),
    [
        (0, "0 B"),
        (1023, "1023 B"),
        (1024, "1,0 KB"),
        (1536, "1,5 KB"),
        (100 * 1024, "100 KB"),
        (1023 * 1024, "1023 KB"),
        (MB, "1,0 MB"),
        (int(4.3 * MB), "4,3 MB"),
        (120 * MB, "120 MB"),
        (1024 * MB, "1,0 GB"),
        (3 * 1024 * MB + 512 * MB, "3,5 GB"),
        (5000 * 1024 * MB, "5000 GB"),
    ],
)
def test_sizes_are_short_and_use_a_comma(size: int, text: str) -> None:
    assert size_text(size) == text
