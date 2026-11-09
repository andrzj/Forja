"""Gera as capturas SVG da tela da Forja em cenários controlados, sem CLI de agente e sem rede.

Uso: uv run python scripts/capturas/tui.py
Grava um SVG por cenário em docs/guia/imagens/.
"""

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tests.ui.install_support import VIEWS as INSTALL_VIEWS  # noqa: E402
from tests.ui.test_live import busy  # noqa: E402

from forja.ui.full import ForjaApp  # noqa: E402
from forja.ui.install_full import InstallApp  # noqa: E402
from forja.ui.theme import THEMES  # noqa: E402
from forja.ui.view import GATE_OF, FeedLine, GateStatus, View  # noqa: E402

OUT = ROOT / "docs" / "guia" / "imagens"
SIZE = (120, 36)


def gates_at(passed: int, running: int = 0, failed: int = 0) -> tuple[tuple[str, GateStatus], ...]:
    """Every check of the 12 gates: gates up to ``passed`` pass, then the running/failed one."""
    result = []
    for name, gate in GATE_OF.items():
        if gate <= passed:
            status = GateStatus.PASSED
        elif gate == running:
            status = GateStatus.RUNNING
        elif gate == failed:
            status = GateStatus.FAILED
        else:
            status = GateStatus.PENDING
        result.append((name, status))
    return tuple(result)


def feed(count: int = 40) -> tuple[FeedLine, ...]:
    kinds = ("read", "edit", "command", "text")
    texts = {
        "read": "leu src/frete/calculo.py",
        "edit": "editou src/frete/calculo.py (+14 -32)",
        "command": "rodou pytest tests/frete -q",
        "text": "separando a regra de desconto da regra de frete",
    }
    return tuple(
        FeedLine(f"12:{n // 60:02d}:{n % 60:02d}", kinds[n % 4], texts[kinds[n % 4]])
        for n in range(count)
    )


ROWS = (
    ("t1", "reduzir a complexidade de montar_pedido (CCN 19)", "integrated"),
    ("t2", "reduzir a complexidade de calcular_frete (CCN 31)", "in_progress"),
    ("t3", "reduzir a complexidade de aplicar_desconto (CCN 17)", "pending"),
    ("t4", "reduzir a complexidade de emitir_nota (CCN 16)", "pending"),
)
LOG = feed()


def running(**changes: object) -> View:
    base: dict[str, object] = dict(
        task_rows=ROWS, task_id="t2", tasks_total=4, tasks_done=1, tasks_integrated=1,
        task_intent="reduzir a complexidade de calcular_frete (CCN 31)", attempt=1,
        gates=gates_at(4, running=5), feed=LOG[-12:], feed_total=len(LOG), log=LOG,
        tokens_used=680_000, tokens_limit=2_000_000, elapsed=761.0, task_tokens=210_000,
    )  # fmt: skip
    return busy(**{**base, **changes})


def rejected() -> View:
    return running(
        attempt=2,
        gates=gates_at(4, failed=5),
        rejections=(
            "t2-a1: tests (gate 5) reprovado: 2 testes falharam em tests/frete/test_calculo.py",
            "t2-a2: tests (gate 5) reprovado: test_frete_com_desconto falhou (esperado 90.0)",
        ),
    )


def blocked() -> View:
    rows = (
        ("t1", "reduzir a complexidade de montar_pedido (CCN 19)", "integrated"),
        ("t2", "reduzir a complexidade de calcular_frete (CCN 31)", "blocked"),
        ("t3", "reduzir a complexidade de aplicar_desconto (CCN 17)", "integrated"),
    )
    return running(
        task_rows=rows, tasks_total=3, tasks_done=3, tasks_integrated=2, tasks_blocked=1,
        gates=gates_at(4, failed=5), state="delivered",
        rejections=("t2-a3: tests (gate 5) reprovado: 3 tentativas sem passar; tarefa bloqueada",),
    )  # fmt: skip


def delivered() -> View:
    rows = tuple((tid, intent, "integrated") for tid, intent, _ in ROWS)
    return running(
        task_rows=rows, tasks_done=4, tasks_integrated=4, state="delivered", task_id="t4",
        gates=gates_at(12), tokens_used=1_240_000, elapsed=2_105.0,
    )  # fmt: skip


async def capture(
    name: str, view: View, theme: str = "escuro", keys: tuple[str, ...] = (),
    final: list[str] | None = None, size: tuple[int, int] = SIZE,
) -> None:  # fmt: skip
    app = ForjaApp(THEMES[theme])
    async with app.run_test(size=size) as pilot:
        app.show(view)
        await pilot.pause()
        if final is not None:
            app.conclude(final)
            await pilot.pause()
        for key in keys:
            await pilot.press(key)
            await pilot.pause()
        write(name, app.export_screenshot(title="forja"))


async def capture_install(name: str, theme: str = "escuro") -> None:
    app = InstallApp(THEMES[theme])
    async with app.run_test(size=SIZE) as pilot:
        app.show(INSTALL_VIEWS["downloading"])
        await pilot.pause()
        write(name, app.export_screenshot(title="forja instalar"))


def write(name: str, svg: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{name}.svg").write_text(svg, encoding="utf-8")
    print(f"{name}.svg")


async def main() -> None:
    await capture("execucao-em-andamento", running())
    await capture("detalhes-da-tarefa", rejected(), keys=("d",), size=(120, 50))
    await capture("atividade-inteira", running(), keys=("l",))
    await capture("rejeicao-de-gate", rejected())
    await capture(
        "entrega-concluida", delivered(), final=[
            "Entregue em forja-run/r1",
            "4 de 4 tarefa(s) integrada(s)",
            "Branch da entrega: forja-run/r1 (sua branch não foi alterada; nada foi enviado).",
            "Resumo: resumo.md",
        ],
    )  # fmt: skip
    await capture(
        "tarefa-bloqueada", blocked(), final=[
            "Entregue em forja-run/r1",
            "2 de 3 tarefa(s) integrada(s); 1 bloqueada(s)",
            "Branch da entrega: forja-run/r1 (sua branch não foi alterada; nada foi enviado).",
        ],
    )  # fmt: skip
    await capture("execucao-interrompida", running(), keys=("q",))
    await capture("barra-de-gates", running(gates=gates_at(6, running=7)), size=(170, 36))
    await capture("tema-claro", running(), theme="claro")
    await capture("tema-dos", running(), theme="dos")
    await capture("ajuda", running(), keys=("question_mark",))
    await capture_install("instalacao")


if __name__ == "__main__":
    asyncio.run(main())
