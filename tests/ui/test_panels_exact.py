"""Every panel rendered at fixed sizes and compared, text and styles, with what it must say."""

import hashlib
import json
from pathlib import Path

import pytest
from rich.text import Text

from forja.ui import panels
from forja.ui.theme import THEMES, with_ascii
from forja.ui.view import FeedLine, GateStatus, View, blank_view
from tests.ui.test_live import busy, gates

GOLDEN = Path(__file__).with_name("panels_golden.json")
THEME = THEMES["escuro"]
ASCII = with_ascii(THEME)

ROWS = (
    ("t1", "primeira tarefa", "integrated"),
    ("t2", "segunda tarefa com um texto mais longo", "integrated"),
    ("t3", "terceira", "in_progress"),
    ("t4", "quarta", "pending"),
    ("t5", "", "blocked"),
    ("t6", "sexta", "pending"),
    ("t7", "setima", "pending"),
)
FEED = tuple(
    FeedLine(f"12:00:0{n}", kind, f"{kind} numero {n}")
    for n, kind in enumerate(("read", "edit", "command", "text", "error", "note", "edit", "text"))
)
MIXED = gates(scope=GateStatus.FAILED, lint=GateStatus.RUNNING, tests=GateStatus.PENDING)


def full(**changes: object) -> View:
    base: dict[str, object] = dict(
        task_rows=ROWS, tasks_total=7, tasks_done=3, tasks_integrated=2, tasks_blocked=1,
        tasks_running=1, feed=FEED, feed_total=8, gates=MIXED,
        rejections=("a: gate 4 (lint): 2 new", "b: gate 6 (tests): 1 failed", "c", "d", "e"),
        rejections_total=5, tokens_used=1_234_567, tokens_limit=3_000_000, elapsed=3725.0,
        task_tokens=45_000,
    )  # fmt: skip
    return busy(**{**base, **changes})


def with_running(running: str | None) -> tuple[tuple[str, str, str], ...]:
    return tuple(
        (
            task,
            intent,
            "in_progress" if task == running else "pending" if state == "in_progress" else state,
        )
        for task, intent, state in ROWS
    )


VIEWS = {
    "full": full(),
    "delivered": full(state="delivered"),
    "failed": full(state="failed", attempt=0),
    "paused": full(state="paused", tasks_running=3, task_number=2),
    "other": full(state="whatever", tokens_used=700, tokens_limit=1000),
    "blank": blank_view(),
    "idle": full(task_rows=with_running(None)),
    "late": full(task_rows=with_running("t7")),
    "over": full(tokens_used=1500, tokens_limit=1000, task_rows=ROWS[:2]),
}  # fmt: skip


def dump(lines: list[Text]) -> list[object]:
    return [
        [
            line.plain,
            str(line.style),
            [[s.start, s.end, str(s.style)] for s in line.spans],
            line.no_wrap,
            line.overflow,
            line.end,
        ]
        for line in lines
    ]


def scenarios() -> dict[str, list[Text]]:
    out: dict[str, list[Text]] = {}
    for key, theme in (("u", THEME), ("a", ASCII)):
        for name, view in VIEWS.items():
            for columns in (*range(1, 12), 12, 30, 50, 70, 90, 130):
                for compact in (False, True):
                    out[f"{key} header {name} {columns} {compact}"] = panels.header(
                        view, theme, columns, compact=compact
                    )
        for columns in range(1, 400):
            out[f"{key} header every {columns}"] = panels.header(
                VIEWS["full"], theme, columns, compact=False
            )
            out[f"{key} header compact every {columns}"] = panels.header(
                VIEWS["paused"], theme, columns, compact=True
            )
            out[f"{key} gates every {columns}"] = [panels.gates_line(VIEWS["full"], theme, columns)]
            out[f"{key} gates blank {columns}"] = [
                panels.gates_line(VIEWS["blank"], theme, columns)
            ]
        for columns in range(1, 110):
            for finished, stopping in ((True, False), (False, True), (False, False)):
                out[f"{key} bar {columns} {finished} {stopping}"] = [
                    panels.footer(theme, columns, finished=finished, stopping=stopping)
                ]
        for columns in range(1, 90):
            out[f"{key} band {columns}"] = [panels.band(theme, columns)]
            out[f"{key} help {columns}"] = panels.help_lines(theme, columns)
    report = ["Entregue", "segunda linha do relatorio", "terceira"]
    for name in ("full", "delivered", "blank", "failed", "idle", "late"):
        view = VIEWS[name]
        for columns in (1, 3, 4, 5, 12, 30, 50, 90):
            for rows in (0, 1, 2, 3, 4, 5, 9):
                out[f"tasks {name} {columns} {rows}"] = panels.tasks(view, THEME, columns, rows)
                out[f"final {name} {columns} {rows}"] = panels.final(
                    report, view, THEME, columns, rows
                )
                out[f"rejections default {name} {columns} {rows}"] = panels.rejections(
                    view, THEME, columns, rows
                )
                out[f"attempt default {name} {columns} {rows}"] = panels.attempt(
                    view, THEME, columns, rows
                )
                for offset in (0, 1, 2, 99):
                    out[f"rejections {name} {columns} {rows} {offset}"] = panels.rejections(
                        view, THEME, columns, rows, offset
                    )
                    for compact in (False, True):
                        out[f"attempt {name} {columns} {rows} {offset} {compact}"] = panels.attempt(
                            view, THEME, columns, rows, offset, compact=compact
                        )
    for key, theme in (("u", THEME), ("a", ASCII)):
        for columns in range(1, 41):
            for compact in (False, True):
                out[f"{key} attempt every {columns} {compact}"] = panels.attempt(
                    VIEWS["full"], theme, columns, 6, compact=compact
                )
                out[f"{key} attempt quiet every {columns} {compact}"] = panels.attempt(
                    VIEWS["blank"], theme, columns, 6, compact=compact
                )
            out[f"{key} tasks every {columns}"] = panels.tasks(VIEWS["full"], theme, columns, 6)
            out[f"{key} rejections every {columns}"] = panels.rejections(
                VIEWS["full"], theme, columns, 3, 1
            )
            out[f"{key} final every {columns}"] = panels.final(
                ["Entregue", "segunda linha"], VIEWS["delivered"], theme, columns, 6
            )
    return out


def digests() -> dict[str, str]:
    """One digest per family of scenarios (the name without its sizes and flags), over every
    scenario's text, styles, spans and line settings, so any change shows which family moved."""
    families: dict[str, list[tuple[str, object]]] = {}
    for name, lines in scenarios().items():
        family = " ".join(w for w in name.split() if not w.isdigit() and w not in ("True", "False"))
        families.setdefault(family, []).append((name, dump(lines)))
    return {
        family: hashlib.sha256(json.dumps(items, ensure_ascii=True).encode()).hexdigest()
        for family, items in sorted(families.items())
    }


def test_the_panels_say_what_they_must_at_every_size() -> None:
    expected = json.loads(GOLDEN.read_text(encoding="utf-8"))
    got = digests()

    assert got.keys() == expected.keys()
    wrong = [family for family in got if got[family] != expected[family]]
    assert wrong == []


@pytest.mark.parametrize(
    ("value", "text"),
    [
        (0, "0"), (999, "999"), (1000, "1k"), (1999, "1k"), (999_999, "999k"),
        (1_000_000, "1M"), (1_099_999, "1M"), (1_100_000, "1.1M"), (2_000_000, "2M"),
        (12_345_678, "12.3M"),
    ],
)  # fmt: skip
def test_short_counts_at_their_edges(value: int, text: str) -> None:
    assert panels.short_count(value) == text
