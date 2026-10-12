"""Plain text: one line for each thing that happens, for logs, pipes and terminals without color.

No cursor movement, no color, no symbols outside ASCII, so the output reads the same in a file,
in a CI log and in any terminal. A line begins with how long the run has been going.
"""

from typing import TextIO

from forja.ui.glyphs import clean
from forja.ui.live import clock_text, percent_text
from forja.ui.view import GateStatus, View


class PlainRenderer:
    def __init__(self, out: TextIO) -> None:
        self._out = out
        self._printed = 0
        self._rejected = 0
        self._task = ""
        self._attempt = 0
        self._gates: dict[str, GateStatus] = {}
        self._state = ""
        self._tenth = 0

    def _line(self, view: View, text: str) -> None:
        self._out.write(f"[{clock_text(view.elapsed)}] {clean(text)}\n")
        self._out.flush()

    def start(self, view: View) -> None:
        self._line(view, f"Forja: {view.objective} em {view.repo} (branch {view.branch})")
        self._line(view, f"isolamento: {view.isolation}")
        self.update(view)

    def update(self, view: View) -> None:
        self._update_state(view)
        self._update_task(view)
        self._update_gates(view)
        self._update_feed(view)
        self._update_rejections(view)
        self._update_tokens(view)

    def _update_state(self, view: View) -> None:
        if view.state != self._state:
            self._state = view.state
            self._line(
                view, f"estado: {view.state}" + (f" ({view.message})" if view.message else "")
            )

    def _update_task(self, view: View) -> None:
        if not view.task_id or (view.task_id, view.attempt) == (self._task, self._attempt):
            return
        if view.task_id != self._task:
            number = min(view.tasks_done + 1, view.tasks_total)
            self._line(view, f"tarefa {number}/{view.tasks_total}: {view.task_intent}")
        if view.attempt:
            self._line(view, f"tentativa {view.attempt}/{view.attempts_max} de {view.task_id}")
        self._task, self._attempt = view.task_id, view.attempt

    def _update_gates(self, view: View) -> None:
        for name, status in view.gates:
            if status in (GateStatus.PASSED, GateStatus.FAILED) and self._gates.get(name) != status:
                self._line(
                    view, f"gate {name}: {'ok' if status is GateStatus.PASSED else 'falhou'}"
                )
            self._gates[name] = status

    def _update_feed(self, view: View) -> None:
        new = min(view.feed_total - self._printed, len(view.feed))
        for item in view.feed[len(view.feed) - new :] if new > 0 else ():
            self._line(view, f"{item.time} {item.text}")
        self._printed = view.feed_total

    def _update_rejections(self, view: View) -> None:
        fresh = min(view.rejections_total - self._rejected, len(view.rejections))
        for rejection in view.rejections[len(view.rejections) - fresh :] if fresh > 0 else ():
            self._line(view, f"rejeitada: {rejection}")
        self._rejected = view.rejections_total

    def _update_tokens(self, view: View) -> None:
        tenth = int(view.tokens_fraction * 10)
        if tenth > self._tenth:
            self._tenth = tenth
            self._line(view, f"tokens: {percent_text(view.tokens_fraction)} do limite")

    def stop(self, view: View) -> None:
        self.update(view)
        done = f"{view.tasks_done}/{view.tasks_total} tarefas"
        if view.tasks_blocked:
            done += f" ({view.tasks_integrated} integrada(s), {view.tasks_blocked} bloqueada(s))"
        self._line(view, f"fim: {view.state}; {done}; tokens {percent_text(view.tokens_fraction)}")
