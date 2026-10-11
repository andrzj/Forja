# 0017. O comando `forja` guia, pergunta pouco e confirma uma vez

## Contexto

O usuário não deve decorar parâmetros. A Forja precisa funcionar também em CI, sem ninguém, e
nunca pode alterar o que o usuário ainda não salvou.

## Decisão

- `forja` sem argumentos detecta (repositório, branch, linguagem, ferramentas, CLIs instaladas),
  pergunta só o que não detectou, prova a CLI do agente com uma tarefa de teste, mostra um resumo e
  pede **uma** confirmação. Depois dela não há mais perguntas.
- Quatro parâmetros: `--escopo`, `--cli`, `--plano` (mostra o que faria, sem executar) e
  `--config` (um `execucao.toml` pronto, para CI). O resto vive em `execucao.toml` (gravado na pasta
  da execução) ou no perfil do usuário, nunca no repositório.
- Verbos: só `refatorar` existe; os outros dizem em que incremento chegam.
- Uma execução incompleta no repositório é oferecida para retomar ou descartar. Descartar marca
  `discarded` e **mostra** os comandos para remover as branches; a Forja não apaga nada.
- Sem terminal (CI, `--config`), uma execução incompleta recusa a partida em vez de decidir sozinha.
- `forja doctor` verifica e explica; não instala. A configuração da CLI do agente é do usuário.
- Códigos de saída: 0 entregue, 1 falhou, 2 não pôde começar, 3 pausada com tudo salvo, 130
  interrompida pelo usuário.

## Consequências

A superfície é pequena e testável sem terminal (o console é uma interface). Instalação assistida
de ferramentas e a fachada `forja agente` ficam para depois.
