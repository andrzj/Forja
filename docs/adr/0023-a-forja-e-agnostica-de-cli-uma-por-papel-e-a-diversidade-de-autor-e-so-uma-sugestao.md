# 0023. A Forja é agnóstica de CLI, com uma CLI por papel; a diversidade de autor é só uma sugestão documentada

## Contexto

A Especificação manda sugerir CLIs diferentes entre testes e implementação. O núcleo já era
agnóstico (contrato `ExecutorAdapter`, `RunConfig.test_author`, mapa papel → runner); o acoplamento
ao Claude Code estava só na camada de CLI. O dono definiu em 21/10 que a Forja funciona com as
principais CLIs (Claude Code, Codex, Cursor, Grok Build; Gemini CLI suspenso), sem adiamento nem
aceite reduzido. Isto substitui as decisões 9 e 10 do `plano-3.md`.

## Decisão

- Há um registro único de CLIs (`forja.executors.KNOWN_CLIS`). Uma CLI nova é um módulo de
  adaptador mais uma linha ali.
- Cada papel tem a sua CLI e o seu modelo, ambos opcionais. `--cli` e `--cli-testes`; `--modelo` e
  `--modelo-testes` (o modelo do autor de testes não herda o do implementador). Sem modelo, a Forja
  não passa flag e vale o que o usuário configurou na CLI.
- **Diversidade de autor é uma sugestão, não um comportamento do software.** A Forja não escolhe,
  não força e não recusa combinações: com a mesma CLI nos dois papéis ela funciona igual. A
  recomendação é usar CLIs (ou ao menos modelos) diferentes para o autor de testes e para o
  implementador, porque um mesmo modelo tende a repetir as mesmas falhas de raciocínio nos testes e
  no código. Quem decide é o usuário, por `--cli-testes`.
- Adaptadores que não impõem a lista de permissões (`enforces_permissions = False`: Codex, Cursor,
  Grok, Gemini) são **registrados**, não recusados: o resumo da execução traz uma linha "Limitação"
  por CLI nessa condição.
- O Gemini CLI fica fora do registro até que a mitigação de `.gemini/settings.json` e `.env` do
  projeto seja feita; reativar é uma linha em `executors/__init__.py`.

## Consequências

O usuário escolhe a combinação; a Forja mostra no resumo quem fez cada papel, com CLI e modelo. A
aceitação do 3f (duas CLIs reais) é o que mede se a diversidade de fato ajuda; até lá a
recomendação acima é uma hipótese, não um resultado medido. Fixtures gravadas e testes `live` dos
adaptadores escritos só pela documentação ficam para o fecho.
