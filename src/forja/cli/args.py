"""The command line: few options, each there for something a person actually needs.

``forja`` alone guides. The verbs are shortcuts for people who know what they want, and four
options cover the rest: where to look (``--escopo``), which agent (``--cli``), what would be done
(``--plano``) and a ready-made answer file for CI (``--config``). Everything else is in
``execucao.toml`` or in the profile, so ``--help`` stays short. ``forja agente`` is for the agents
and does not appear in the help.
"""

import argparse
from dataclasses import dataclass, field
from pathlib import Path

VERBS = {
    "refatorar": "melhora o código sem mudar o comportamento",
    "corrigir": "corrige um erro descrito por você (incremento 3)",
    "criar": "cria um projeto a partir de uma ideia (incremento 6)",
    "documentar": "entende o código e escreve a documentação (incremento 4)",
    "investigar": "investiga uma dúvida ou um erro, sem alterar código (incremento 6)",
}
AGENT_COMMANDS = ("testar", "medir", "lint")


@dataclass(frozen=True)
class Arguments:
    command: str = ""  # "", a verb, "doctor" or "agente"
    text: str = ""
    file: Path | None = None
    criteria: Path | None = None
    scope: tuple[str, ...] = ()
    cli: str = ""
    plan_only: bool = False
    config: Path | None = None
    agent: tuple[str, ...] = field(default=())


def parser() -> argparse.ArgumentParser:
    main = argparse.ArgumentParser(
        prog="forja",
        description="Conduz um agente de código com portões determinísticos. "
        "Sem argumentos, ele guia você.",
    )
    main.add_argument("--escopo", action="append", metavar="CAMINHO", help="só olhar este caminho")
    main.add_argument("--cli", metavar="NOME", help="qual agente usar (claude-code)")
    main.add_argument("--plano", action="store_true", help="mostrar o plano, sem executar")
    main.add_argument(
        "--config", type=Path, metavar="ARQUIVO", help="rodar com execucao.toml, sem perguntas"
    )
    sub = main.add_subparsers(dest="command", metavar="COMANDO")
    for verb, help_text in VERBS.items():
        item = sub.add_parser(verb, help=help_text)
        item.add_argument("texto", nargs="?", default="", help="descrição, se o comando pedir")
        item.add_argument("-f", "--arquivo", type=Path, help="ler a descrição deste arquivo")
        if verb == "corrigir":
            item.add_argument(
                "--criterios", type=Path, metavar="ARQUIVO", help="critérios (JSON) do conserto"
            )
        item.add_argument("--escopo", action="append", metavar="CAMINHO", default=argparse.SUPPRESS)
        item.add_argument("--cli", metavar="NOME", default=argparse.SUPPRESS)
        item.add_argument("--plano", action="store_true", default=argparse.SUPPRESS)
    sub.add_parser("doctor", help="verifica se o ambiente está pronto")
    agent = sub.add_parser("agente")  # for the agents: left out of the help
    agent.add_argument("what", choices=AGENT_COMMANDS)
    agent.add_argument("rest", nargs="*")
    sub._choices_actions = [a for a in sub._choices_actions if a.dest != "agente"]  # noqa: SLF001
    return main


def parse(argv: list[str] | None = None) -> Arguments:
    found = parser().parse_args(argv)
    command = found.command or ""
    return Arguments(
        command=command,
        text=getattr(found, "texto", "") or "",
        file=getattr(found, "arquivo", None),
        criteria=getattr(found, "criterios", None),
        scope=tuple(found.escopo or ()),
        cli=found.cli or "",
        plan_only=bool(found.plano),
        config=found.config,
        agent=(found.what, *found.rest) if command == "agente" else (),
    )
