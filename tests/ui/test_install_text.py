"""The installation on the live line and in plain text, fed by made-up events."""

import io

import pytest

from forja.ui.install_events import InstallEvent, InstallView, Stage
from forja.ui.install_text import InstallLiveRenderer, InstallPlainRenderer, render_status
from forja.ui.theme import THEMES, with_ascii
from tests.ui.install_support import (
    HOSTILE,
    MB,
    MID,
    VIEWS,
    at,
    downloading,
    played,
    started,
    success,
    with_failure,
)
from tests.ui.test_live import DEPTHS, WIDTHS, caps

DEPTH_THEMES = list(THEMES.values())


def lines_of(text: str) -> list[str]:
    return text.splitlines()


def drive(renderer: object, events: list[InstallEvent]) -> None:
    """Feed the renderer the view after each event, as the installer would."""
    for number in range(1, len(events) + 1):
        view = played(*events[:number])
        if number == 1:
            renderer.start(view)  # type: ignore[attr-defined]
        else:
            renderer.update(view)  # type: ignore[attr-defined]
        if view.finished:
            renderer.stop(view)  # type: ignore[attr-defined]


# -- plain text ---------------------------------------------------------------------------------


def plain_output(events: list[InstallEvent]) -> list[str]:
    out = io.StringIO()
    drive(InstallPlainRenderer(out), events)
    return lines_of(out.getvalue())


def test_plain_text_tells_each_tool_up_front_then_each_thing_that_happens() -> None:
    assert plain_output(with_failure()) == [
        "[00:35] instalação: 4 ferramenta(s) em C:\\Users\\ana\\.forja\\ferramentas",
        "[00:35] - gitleaks 8.21.2: procura segredos no código; "
        "origem github.com/gitleaks/gitleaks; tamanho 8,0 MB",
        "[00:35] - semgrep 1.95.0: análise estática de segurança; "
        "origem pypi.org/project/semgrep; tamanho 40,0 MB",
        "[00:35] - osv-scanner 1.9.1: audita dependências conhecidas; "
        "origem github.com/google/osv-scanner; tamanho 12,0 MB",
        "[00:35] - jscpd 4.0.5: acha código duplicado; "
        "origem npmjs.com/package/jscpd; tamanho 2,0 MB",
        "[00:35] gitleaks: baixando (8,0 MB)",
        "[00:35] gitleaks: baixando 100%",
        "[00:35] gitleaks: conferindo checksum",
        "[00:35] gitleaks: extraindo",
        "[00:35] gitleaks: verificando",
        "[00:35] gitleaks: pronta",
        "[00:35] semgrep: baixando (40,0 MB)",
        "[00:35] semgrep: baixando 25%",
        "[00:35] semgrep: falhou: o servidor pypi.org não respondeu (tempo esgotado)",
        "[00:35] semgrep: o que fazer: confira a rede",
        "[00:35] osv-scanner: já instalada",
        "[00:35] jscpd: falhou: checksum diferente do esperado",
        "[00:35] jscpd: o que fazer: rode forja instalar de novo",
        "[00:35] A instalação terminou com falhas: 2 de 4 ferramenta(s) não foram instaladas.",
        "[00:35] Instaladas (1): gitleaks 8.21.2",
        "[00:35] Já instaladas (1): osv-scanner 1.9.1",
        "[00:35] Onde: C:\\Users\\ana\\.forja\\ferramentas",
        "[00:35] Falhou: semgrep 1.95.0 (pypi.org/project/semgrep): "
        "o servidor pypi.org não respondeu (tempo esgotado)",
        "[00:35] O que fazer: confira a rede",
        "[00:35] Falhou: jscpd 4.0.5 (npmjs.com/package/jscpd): checksum diferente do esperado",
        "[00:35] O que fazer: rode forja instalar de novo",
        "[00:35] Tempo: 00:35",
        "[00:35] Para remover as ferramentas, apague a pasta; a Forja não apaga nada.",
    ]


def test_plain_text_reports_the_download_by_quarters_and_never_twice() -> None:
    gone: list[InstallEvent] = [started()]
    gone += [downloading("gitleaks", step * MB // 2) for step in range(0, 17)]
    said = [line for line in plain_output(gone) if "baixando" in line]
    assert [line.split("] ")[1] for line in said] == [
        "gitleaks: baixando (8,0 MB)",
        "gitleaks: baixando 25%",
        "gitleaks: baixando 50%",
        "gitleaks: baixando 75%",
        "gitleaks: baixando 100%",
    ]
    out = io.StringIO()
    renderer = InstallPlainRenderer(out)
    view = played(*MID)
    renderer.start(view)
    renderer.update(view)
    renderer.update(view)
    assert out.getvalue().count("baixando 25%") == 1
    assert out.getvalue().count("baixando (8,0 MB)") == 1


def test_plain_text_of_a_good_run_ends_with_what_was_installed_and_where() -> None:
    lines = plain_output(success())
    assert "[00:35] Instalação concluída." in lines
    assert "[00:35] jscpd: já instalada" in lines
    assert "[00:35] Instaladas (3): gitleaks 8.21.2, semgrep 1.95.0, osv-scanner 1.9.1" in lines
    assert lines[-1].endswith("a Forja não apaga nada.")
    assert sum("pronta" in line for line in lines) == 3


def test_plain_text_marks_the_time_since_the_start_and_is_flushed_line_by_line() -> None:
    class Spy(io.StringIO):
        flushes = 0

        def flush(self) -> None:
            self.flushes += 1

    out = Spy()
    renderer = InstallPlainRenderer(out)
    renderer.start(played(started(), seconds=3725.0))
    assert out.getvalue().splitlines()[0].startswith("[1:02:05] instalação:")
    assert out.flushes == len(out.getvalue().splitlines())


def test_plain_text_stop_says_the_end_even_without_a_finished_event() -> None:
    out = io.StringIO()
    renderer = InstallPlainRenderer(out)
    view = played(*MID)
    renderer.start(view)
    renderer.stop(view)
    assert "A instalação parou: 4 ferramenta(s) ficaram sem instalar." in out.getvalue()


def test_plain_text_cannot_be_made_to_move_the_terminal() -> None:
    out = io.StringIO()
    renderer = InstallPlainRenderer(out)
    view = VIEWS["hostile"]
    renderer.start(view)
    renderer.update(view)
    renderer.stop(view)
    text = out.getvalue()
    assert not set(text) & set("\x1b\x07\r\t‮")
    assert "pwned" in text


# -- the live line ------------------------------------------------------------------------------


def live_output(events: list[InstallEvent], **changes: object) -> str:
    out = io.StringIO()
    drive(
        InstallLiveRenderer(THEMES["escuro"], caps(**{"colors": "none", **changes}), out=out),
        events,
    )
    return out.getvalue()


@pytest.mark.parametrize("name", list(VIEWS))
def test_the_live_lines_are_three_and_never_wider_than_the_window(name: str) -> None:
    for theme in (THEMES["escuro"], with_ascii(THEMES["neon"])):
        for columns in WIDTHS:
            lines = render_status(VIEWS[name], theme, columns)
            assert len(lines) == 3
            assert all(line.cell_len <= columns for line in lines), (name, columns)


def test_the_live_lines_say_the_tool_at_work_how_far_it_is_and_what_waits() -> None:
    lines = render_status(played(*MID), THEMES["escuro"], 80)
    assert [line.plain for line in lines] == [
        " ▶ gitleaks 8.21.2 · baixando 25%",
        " total █░░░░░░░░░░░░░░░░░░░░░░░ 3% 0/4 ferramentas · 00:35",
        " na fila: semgrep, osv-scanner, jscpd",
    ]
    done = render_status(VIEWS["done"], THEMES["escuro"], 80)
    assert done[2].plain.strip() == ""
    assert done[0].plain == " nada em andamento"


def test_the_live_queue_line_is_cut_at_the_width_with_an_ellipsis() -> None:
    line = render_status(VIEWS["queued"], THEMES["escuro"], 20)[2]
    assert line.plain == " na fila: gitleaks,…"
    assert render_status(VIEWS["queued"], with_ascii(THEMES["escuro"]), 20)[2].plain == (
        " na fila: gitleak..."
    )


def test_the_live_renderer_says_each_tool_once_when_it_settles() -> None:
    text = live_output(with_failure())
    assert "Forja · instalação das ferramentas · 4 ferramenta(s) em" in text
    assert text.count("✓ gitleaks 8.21.2 instalada (8,0 MB)") == 1
    assert text.count("✓ osv-scanner 1.9.1 já instalada") == 1
    assert text.count("✗ semgrep 1.95.0 falhou: o servidor pypi.org não respondeu") == 1
    assert text.count("o que fazer: confira a rede") >= 1
    assert text.count("o que fazer: rode forja instalar de novo") >= 1


def test_the_live_renderer_updating_twice_prints_nothing_new() -> None:
    out = io.StringIO()
    renderer = InstallLiveRenderer(THEMES["escuro"], caps(colors="none"), out=out)
    view = played(started(), at("jscpd", Stage.PRESENT))
    renderer.start(view)
    renderer.update(view)
    renderer.update(view)
    assert out.getvalue().count("jscpd 4.0.5 já instalada") == 1


def test_the_live_renderer_ends_with_the_report_wrapped_not_cut() -> None:
    text = live_output(with_failure(), columns=60)
    tail = text[text.rindex("A instalação terminou") :]
    assert "A instalação terminou com falhas: 2 de 4" in tail
    assert "esgotado)" in tail  # the reason is whole, on the next line
    assert "Instaladas (1): gitleaks 8.21.2" in tail
    assert "Para remover as ferramentas, apague a pasta" in tail
    assert all(len(line) <= 60 for line in tail.splitlines())


def test_the_live_report_of_a_good_run() -> None:
    text = live_output(success())
    assert "Instalação concluída." in text
    assert "Instaladas (3): gitleaks 8.21.2, semgrep 1.95.0, osv-scanner 1.9.1" in text
    assert "falhou" not in text


@pytest.mark.parametrize("colors", DEPTHS)
def test_the_live_renderer_works_at_every_depth_of_color(colors: str) -> None:
    text = live_output(with_failure(), colors=colors)
    assert "Forja" in text and "Instaladas (1)" in text


def test_the_live_renderer_with_hostile_text_does_not_move_the_terminal() -> None:
    out = io.StringIO()
    renderer = InstallLiveRenderer(THEMES["escuro"], caps(colors="none"), out=out)
    view: InstallView = VIEWS["hostile"]
    renderer.start(view)
    renderer.update(view)
    renderer.stop(view)
    text = out.getvalue()
    for sequence in ("\x1b]0;", "\x1b[2J", "\x07", "‮"):
        assert sequence not in text
    assert HOSTILE.replace("\x1b", "") not in text


def test_the_live_renderer_survives_a_stop_without_a_start() -> None:
    out = io.StringIO()
    renderer = InstallLiveRenderer(THEMES["escuro"], caps(colors="none"), out=out)
    renderer.stop(VIEWS["done"])
    assert "Instalação concluída." in out.getvalue()
