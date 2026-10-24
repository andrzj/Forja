# 0026. O registro de mudança é escrito pela Forja e a documentação tem commits próprios

## Contexto

A Especificação manda que a parte factual do registro de mudança seja gerada pela ferramenta e que o modelo escreva só o porquê e o impacto, sob verificação de citações. Manda também que o README tenha commit próprio (`docs(readme):`) e que os tipos de commit não se misturem (`docs:` só toca documentação). Não diz onde o registro fica nem como garantir a regra dos tipos de commit.

## Decisão

- **A Forja escreve o registro; o agente não.** O agente declara afirmações com citação e a Forja monta `docs/mudancas/<tarefa>.md` com os fatos que ela mediu (arquivos e símbolos do diff, métricas, gates aprovados, ferramentas, commit para reverter) e com a seção “Porquê e impacto” feita só das afirmações validadas. O que o agente escrever nesse caminho é sobrescrito. Assim o agente nunca altera um fato, e o gate `change_record` confere só o que sai do diff.
- **O caminho é fixo:** `docs/mudancas/<tarefa>.md`, um arquivo por tarefa, no commit `docs:` da tarefa. O escopo do documentador recusa qualquer outro arquivo dessa pasta.
- **Commits.** Registro e ADR vão em `docs:`. O README vai antes, num commit `docs(readme):` sem o trailer `Stage-Id`; só o commit final da etapa o leva, então uma retomada no meio refaz só o que falta.
- **Não há validador de tipo de commit.** O escopo do papel (só arquivos de documentação, nunca instrução de agente nem pasta oculta) já garante que `docs:` só toca documentação, do mesmo modo que o escopo do autor de testes garante `test:`.

## Alternativas

- *O agente escreve o registro inteiro e um gate o compara com o diff.* Mais flexível, mas o gate teria de reconhecer cada fato em prosa livre, e uma frase sem citação passaria.
- *Chave `[documentation] changes_dir` no `forja.toml`.* Considerada e não construída: ninguém pediu outro caminho, e mudá-lo depois custa uma constante e uma chave.
- *Um validador de tipo de commit.* Duplicaria o que o escopo já impõe.

## Consequências

O registro é determinístico e reproduzível, e um agente defeituoso não consegue falsificá-lo. O custo é que o texto do agente só entra pelo que for citado: frase sem citação não aparece, e o que as linhas citadas dizem continua sendo conferência do revisor. Os dois commits de documentação deixam o README fácil de reverter sozinho. O uso está em `docs/documentacao-gerada.md`; o plano, em `docs/plano-documentador.md`.
