"""What the agent or a file name says may be read on the screen and nothing more.

A terminal obeys escape sequences: to rewrite the title, to move the cursor over earlier lines,
to hide text, to write to the clipboard. Everything the screen shows from outside is cleaned.
"""

import io

import pytest

from forja.core.states import AttemptState, Level, TaskState
from forja.ui.glyphs import clean, fit, fit_path
from forja.ui.live import LiveRenderer, render_status
from forja.ui.plain import PlainRenderer
from forja.ui.terminal import Capabilities
from forja.ui.theme import THEMES
from tests.ui.support import activity, model, transition

TITLE = "\x1b]0;pwned\x07"
CLEAR = "\x1b[2J\x1b[H"
CLIPBOARD = "\x1b]52;c;ZXZpbA==\x07"
HIDE = "\x1b[8m"
BIDI = "‮"
ATTACKS = [TITLE, CLEAR, CLIPBOARD, HIDE, "\x9b31m", "a\rb", BIDI + "txt.exe", "\x00\x07\x08\x7f"]


@pytest.mark.parametrize("attack", ATTACKS)
def test_no_control_character_survives_cleaning(attack: str) -> None:
    cleaned = clean(f"before {attack} after")

    assert "\x1b" not in cleaned
    assert not any(ord(char) < 32 or 127 <= ord(char) < 160 for char in cleaned)
    assert BIDI not in cleaned
    assert cleaned.startswith("before ")
    assert cleaned.endswith(" after")


def test_line_breaks_and_tabs_become_spaces_so_a_line_cannot_pose_as_two() -> None:
    assert clean("a\nb\r\nc\td") == "a b  c d"


def test_ordinary_text_is_left_alone() -> None:
    text = "reduzir a complexidade de calcular_frete → ✓ ░ 日本語"

    assert clean(text) == text


def test_shortening_cleans_too() -> None:
    assert "\x1b" not in fit(TITLE + "x" * 100, 20)
    assert "\x1b" not in fit_path(CLEAR + "src/a.py", 40)


def feed_attack(attack: str):  # type: ignore[no-untyped-def]
    view = model(
        objective=attack + "refatorar", repo=attack + "repo", branch=attack, isolation=attack
    )
    view.apply(
        transition(Level.TASK, "t1", TaskState.PENDING, payload={"intent": attack + "reduce"})
    )
    view.apply(transition(Level.TASK, "t1", TaskState.IN_PROGRESS))
    view.apply(activity("file_read", path=attack + "src/a.py"))
    view.apply(activity("file_edit", path=attack + "src/a.py", added=1, removed=0))
    view.apply(activity("command", command=attack + "ls"))
    view.apply(activity("text", text=attack + "pronto"))
    view.apply(activity("error", message=attack + "falhou"))
    view.apply(
        transition(Level.ATTEMPT, "t1-a1", AttemptState.REJECTED, payload={"reason": attack + "x"})
    )
    view.apply(transition(Level.EXECUTION, "r1", "paused", payload={"reason": attack + "why"}))
    return view


@pytest.mark.parametrize("attack", ATTACKS)
def test_the_view_holds_nothing_a_terminal_could_obey(attack: str) -> None:
    snapshot = feed_attack(attack).snapshot()

    shown = [
        snapshot.objective, snapshot.repo, snapshot.branch, snapshot.isolation, snapshot.message,
        snapshot.task_intent, *snapshot.rejections, *(line.text for line in snapshot.feed),
    ]  # fmt: skip
    for text in shown:
        assert clean(text) == text, repr(text)


@pytest.mark.parametrize("attack", ATTACKS)
def test_plain_text_carries_no_escape_code_from_outside(attack: str) -> None:
    out = io.StringIO()
    renderer = PlainRenderer(out)
    view = feed_attack(attack).snapshot()

    renderer.start(view)
    renderer.update(view)
    renderer.stop(view)

    assert "\x1b" not in out.getvalue()
    assert "\r" not in out.getvalue().replace("\r\n", "")


@pytest.mark.parametrize("attack", ATTACKS)
@pytest.mark.parametrize("theme", THEMES.values(), ids=lambda theme: theme.key)
def test_the_live_lines_carry_no_escape_code_from_outside(attack: str, theme) -> None:  # type: ignore[no-untyped-def]
    for line in render_status(feed_attack(attack).snapshot(), theme, 100, "none"):
        assert "\x1b" not in line.plain
        assert "\r" not in line.plain


@pytest.mark.parametrize("attack", [TITLE, CLEAR, CLIPBOARD])
def test_what_the_live_renderer_prints_above_the_lines_has_no_escape_code_from_outside(
    attack: str,
) -> None:
    caps = Capabilities(True, "none", True, 100, 30, "xterm", True, False, False)
    out = io.StringIO()
    renderer = LiveRenderer(THEMES["escuro"], caps, out=out)
    view = feed_attack(attack).snapshot()

    renderer.start(view)
    renderer.update(view)
    renderer.stop(view)

    text = out.getvalue()
    for sequence in ("\x1b]0;", "\x1b[2J", "\x1b]52;"):
        assert sequence not in text
