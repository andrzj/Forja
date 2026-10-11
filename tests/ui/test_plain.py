"""Plain text: a line for each thing that happens, readable in a file and made of ASCII."""

import io

from forja.ui.plain import PlainRenderer
from forja.ui.view import FeedLine, GateStatus, blank_view
from tests.ui.test_live import busy, gates


def lines(out: io.StringIO) -> list[str]:
    return out.getvalue().splitlines()


def test_the_start_says_what_the_run_is_and_where_it_is_isolated() -> None:
    out = io.StringIO()
    renderer = PlainRenderer(out)

    renderer.start(busy(state="preparing", feed=(), feed_total=0))

    assert lines(out)[0] == "[12:31] Forja: refatorar em meu-servico (branch forja/r1)"
    assert lines(out)[1] == "[12:31] isolamento: WSL isolado"
    assert "[12:31] estado: preparing" in lines(out)


def test_a_new_task_and_a_new_attempt_are_announced_once() -> None:
    out = io.StringIO()
    renderer = PlainRenderer(out)
    view = busy(gates=gates(lint=GateStatus.PENDING), feed=(), feed_total=0)

    renderer.start(view)
    renderer.update(view)
    renderer.update(busy(attempt=2, gates=view.gates, feed=(), feed_total=0))

    text = out.getvalue()
    assert text.count("tarefa 3/5: reduzir a complexidade") == 1
    assert text.count("tentativa 1/3 de t3") == 1
    assert text.count("tentativa 2/3 de t3") == 1


def test_a_gate_is_reported_when_it_passes_or_fails_and_not_again() -> None:
    out = io.StringIO()
    renderer = PlainRenderer(out)

    renderer.start(busy(gates=gates(), feed=(), feed_total=0))
    renderer.update(busy(gates=gates(lint=GateStatus.FAILED), feed=(), feed_total=0))
    renderer.update(busy(gates=gates(lint=GateStatus.FAILED), feed=(), feed_total=0))

    text = out.getvalue()
    assert text.count("gate scope: ok") == 1
    assert text.count("gate lint: falhou") == 1
    assert "gate build" not in text


def test_the_news_of_the_agent_and_the_rejections_are_printed_once() -> None:
    out = io.StringIO()
    renderer = PlainRenderer(out)
    view = busy(
        feed=(FeedLine("12:31:07", "edit", "editou src/a.py (+1 -1)"),), feed_total=1,
        rejections=("t3-a1: gate 4 (lint): 2 new",), rejections_total=1,
    )  # fmt: skip

    renderer.start(view)
    renderer.update(view)

    text = out.getvalue()
    assert text.count("12:31:07 editou src/a.py (+1 -1)") == 1
    assert text.count("rejeitada: t3-a1: gate 4 (lint): 2 new") == 1


def test_the_tokens_are_reported_each_time_a_new_tenth_of_the_limit_is_reached() -> None:
    out = io.StringIO()
    renderer = PlainRenderer(out)

    for used in (50, 120, 190, 430, 430, 1010):
        renderer.update(busy(tokens_used=used, tokens_limit=1000, feed=(), feed_total=0))

    reported = [line for line in lines(out) if "tokens:" in line]
    assert [line.split("tokens: ")[1] for line in reported] == [
        "12% do limite",
        "43% do limite",
        "101% do limite",
    ]


def test_the_end_is_one_line_with_the_state_the_tasks_and_the_tokens() -> None:
    out = io.StringIO()
    renderer = PlainRenderer(out)

    renderer.stop(busy(state="delivered", tasks_done=5, feed=(), feed_total=0))

    assert lines(out)[-1] == "[12:31] fim: delivered; 5/5 tarefas; tokens 43%"


def test_a_state_with_a_reason_shows_it() -> None:
    out = io.StringIO()
    renderer = PlainRenderer(out)

    renderer.update(blank_view(state="paused", message="interrupted"))

    assert "estado: paused (interrupted)" in out.getvalue()


def test_what_the_renderer_writes_by_itself_is_ascii() -> None:
    out = io.StringIO()
    renderer = PlainRenderer(out)
    view = busy(
        task_intent="reduce f", feed=(FeedLine("12:31:07", "edit", "editou a.py (+1 -1)"),),
        feed_total=1, rejections=("t3-a1: gate 4 (lint): x",), rejections_total=1,
    )  # fmt: skip

    renderer.start(view)
    renderer.update(busy(state="delivered", gates=gates(lint=GateStatus.PASSED)))
    renderer.stop(view)

    assert out.getvalue().isascii()
