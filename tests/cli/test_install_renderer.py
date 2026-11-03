"""``install_renderer_for``: the screen is chosen as for a run."""

import threading
from collections.abc import Callable
from pathlib import Path

import pytest

from forja.cli.install import _watched, install_renderer_for
from forja.cli.settings import Execucao, Interface, Perfil
from forja.ui import terminal
from forja.ui.glyphs import ASCII
from forja.ui.install_full import InstallFullRenderer
from forja.ui.install_text import InstallLiveRenderer, InstallPlainRenderer
from forja.ui.terminal import Capabilities
from forja.ui.theme import CLARO, ESCURO


class Said:
    def __init__(self) -> None:
        self.lines: list[str] = []

    def say(self, text: str = "") -> None:
        self.lines.append(text)


def caps(
    *,
    interactive: bool = True,
    unicode: bool = True,
    columns: int = 120,
    rows: int = 36,
    dark: bool | None = True,
) -> Capabilities:
    return Capabilities(
        interactive=interactive, colors="truecolor", unicode=unicode, columns=columns, rows=rows,
        program="test", dark_background=dark, can_resize=False, reduced_motion=False,
    )  # fmt: skip


def choose(
    monkeypatch: pytest.MonkeyPatch,
    found: Capabilities,
    interface: Interface | None = None,
    saved: Interface | None = None,
) -> tuple[object, Said]:
    monkeypatch.setattr(terminal, "detect", lambda: found)
    said = Said()
    profile = Perfil(interface=interface or Interface())
    execution = Execucao(interface=saved) if saved else None
    return install_renderer_for(profile, execution, said), said  # type: ignore[arg-type]


def test_a_pipe_gets_plain_text(monkeypatch: pytest.MonkeyPatch) -> None:
    screen, said = choose(monkeypatch, caps(interactive=False))

    assert isinstance(screen, InstallPlainRenderer)
    assert said.lines == []


def test_a_roomy_terminal_gets_the_full_screen(monkeypatch: pytest.MonkeyPatch) -> None:
    screen, _ = choose(monkeypatch, caps())

    assert isinstance(screen, InstallFullRenderer)


def test_the_live_line_is_chosen_by_the_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    screen, _ = choose(monkeypatch, caps(), Interface(modo="linha"))

    assert isinstance(screen, InstallLiveRenderer)


def test_a_small_window_says_why_it_falls_to_the_live_line(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    screen, said = choose(monkeypatch, caps(columns=50))

    assert isinstance(screen, InstallLiveRenderer)
    assert said.lines == ["a janela está pequena (50x36); a tela completa pede ao menos 60x16"]


def test_the_saved_interface_wins_over_the_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    screen, _ = choose(monkeypatch, caps(), Interface(modo="texto"), Interface(modo="linha"))

    assert isinstance(screen, InstallLiveRenderer)


def test_the_theme_follows_the_background_or_the_name(monkeypatch: pytest.MonkeyPatch) -> None:
    light, _ = choose(monkeypatch, caps(dark=False), Interface(modo="linha"))
    dark, _ = choose(monkeypatch, caps(dark=True), Interface(modo="linha"))
    named, _ = choose(monkeypatch, caps(dark=True), Interface(modo="linha", tema="claro"))

    assert isinstance(light, InstallLiveRenderer)
    assert isinstance(dark, InstallLiveRenderer)
    assert isinstance(named, InstallLiveRenderer)
    assert (light.theme, dark.theme, named.theme) == (CLARO, ESCURO, CLARO)


@pytest.mark.parametrize(
    ("found", "interface", "ascii_symbols"),
    [
        (caps(unicode=False), Interface(modo="linha"), True),
        (caps(), Interface(modo="linha", ascii=True), True),
        (caps(), Interface(modo="linha"), False),
    ],
)
def test_ascii_symbols_when_asked_or_when_unicode_is_missing(
    monkeypatch: pytest.MonkeyPatch, found: Capabilities, interface: Interface, ascii_symbols: bool
) -> None:
    screen, _ = choose(monkeypatch, found, interface)

    assert isinstance(screen, InstallLiveRenderer)
    assert (screen.theme.glyphs is ASCII) is ascii_symbols


def test_the_watcher_thread_does_not_hold_the_process_open(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    daemons: list[bool] = []

    class Spy(threading.Thread):
        def __init__(self, *args: object, **kwargs: object) -> None:
            super().__init__(*args, **kwargs)  # type: ignore[arg-type]
            daemons.append(self.daemon)

    monkeypatch.setattr(threading, "Thread", Spy)
    fetch: Callable[[str, Path, int], None] = lambda url, destination, limit: None  # noqa: E731

    _watched(fetch, lambda size: None)("https://x", tmp_path / "f", 1)

    assert daemons == [True]
