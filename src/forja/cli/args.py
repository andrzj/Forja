"""The command line: few options, each there for something a person actually needs.

``forja`` alone guides. The verbs are shortcuts for people who know what they want, and a few
options cover the rest: where to look (``--escopo``), which agent (``--cli``, and ``--cli-testes``
for the one that writes the tests of a fix), the Semgrep rules the user supplies
(``--semgrep-config``), what would be done (``--plano``) and a ready-made answer file for CI
(``--config``). Everything else is in ``execucao.toml`` or in the profile, so
``--help`` stays short. ``forja agente`` is for the agents and does not appear in the help.
"""

import argparse
from dataclasses import dataclass, field
from pathlib import Path

from forja.executors import KNOWN_CLIS

VERBS = {
    "refatorar": "melhora o código sem mudar o comportamento",
    "corrigir": "corrige um erro descrito por você (incremento 3)",
    "criar": "cria um projeto a partir de uma ideia (incremento 6)",
    "investigar": "entende o código a partir de uma pergunta e escreve a documentação",
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
    cli_tests: str = ""
    model: str = ""
    model_tests: str = ""
    plan_only: bool = False
    config: Path | None = None
    semgrep_config: str = ""  # text, so a registry reference is seen as typed
    facts: Path | None = None
    run: str = ""  # revisao: the run to read; empty is the newest of the repository
    main_ref: str = ""  # revisao: the main branch; empty is origin/HEAD
    agent: tuple[str, ...] = field(default=())


def parser() -> argparse.ArgumentParser:
    main = argparse.ArgumentParser(
        prog="forja",
        description="Conduz um agente de código com portões determinísticos. "
        "Sem argumentos, ele guia você.",
    )
    main.add_argument("--escopo", action="append", metavar="CAMINHO", help="só olhar este caminho")
    main.add_argument("--cli", metavar="NOME", help=f"qual agente usar ({', '.join(KNOWN_CLIS)})")
    main.add_argument(
        "--cli-testes",
        metavar="NOME",
        help="qual CLI escreve os testes do conserto (corrigir); padrão: a de --cli",
    )
    main.add_argument(
        "--modelo",
        metavar="NOME",
        help="qual modelo a CLI usa; padrão: o que está configurado nela",
    )
    main.add_argument(
        "--modelo-testes",
        metavar="NOME",
        help="qual modelo escreve os testes do conserto (corrigir); padrão: o configurado na CLI",
    )
    main.add_argument("--plano", action="store_true", help="mostrar o plano, sem executar")
    main.add_argument(
        "--semgrep-config",
        metavar="CAMINHO",
        help="regras do Semgrep (arquivo ou diretório) que você fornece; a Forja não traz regras. "
        "Sem elas, e sem .semgrep.yml ou .semgrep/ no repositório, a análise SAST não executa",
    )
    main.add_argument(
        "--fatos",
        type=Path,
        metavar="ARQUIVO",
        help="fatos que você registrou (uma linha por fato: id | autor | data | texto); "
        "entram nos pacotes dos agentes como evidência",
    )
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
                "--criterios",
                type=Path,
                metavar="ARQUIVO",
                help="critérios (JSON) do conserto; sem eles, um agente os escreve da descrição",
            )
        item.add_argument("--escopo", action="append", metavar="CAMINHO", default=argparse.SUPPRESS)
        item.add_argument("--cli", metavar="NOME", default=argparse.SUPPRESS)
        item.add_argument("--cli-testes", metavar="NOME", default=argparse.SUPPRESS)
        item.add_argument("--modelo", metavar="NOME", default=argparse.SUPPRESS)
        item.add_argument("--modelo-testes", metavar="NOME", default=argparse.SUPPRESS)
        item.add_argument("--plano", action="store_true", default=argparse.SUPPRESS)
        item.add_argument("--semgrep-config", metavar="CAMINHO", default=argparse.SUPPRESS)
        item.add_argument("--fatos", type=Path, metavar="ARQUIVO", default=argparse.SUPPRESS)
    sub.add_parser("doctor", help="verifica se o ambiente está pronto")
    review = sub.add_parser(
        "revisao",
        help="depois do `git fetch`, diz o que de uma execução chegou à branch principal",
    )
    review.add_argument(
        "execucao", nargs="?", default="", help="id da execução; padrão: a mais recente"
    )
    review.add_argument(
        "--principal",
        metavar="REF",
        default="",
        help="a branch principal a ler, como origin/main; padrão: origin/HEAD",
    )
    review.add_argument(
        "--fatos",
        type=Path,
        metavar="ARQUIVO",
        default=argparse.SUPPRESS,
        help="comentários e confirmações do revisor (uma linha por fato)",
    )
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
        cli_tests=found.cli_testes or "",
        model=found.modelo or "",
        model_tests=found.modelo_testes or "",
        plan_only=bool(found.plano),
        config=found.config,
        semgrep_config=found.semgrep_config or "",
        facts=found.fatos,
        run=getattr(found, "execucao", "") or "",
        main_ref=getattr(found, "principal", "") or "",
        agent=(found.what, *found.rest) if command == "agente" else (),
    )
