# 0001. Sem PR: a entrega é a branch mais o resumo

- Status: Aceito (a parte do push foi substituída pelo [ADR 0013](0013-a-forja-nunca-faz-push.md))
- Data: 10/10/2026

## Contexto

A primeira versão da especificação previa que a Forja criasse um pull request numa plataforma de hospedagem (operação "Criação do PR" da tabela de idempotência). O plano deixava a plataforma em aberto (questão 5), e cada plataforma exigiria uma integração, credenciais e um reconciliador próprio.

## Decisão

A Forja não abre PR e não se integra a nenhuma plataforma. A entrega é a branch da execução, enviada ao remoto só se o usuário concedeu o push na preparação, mais o arquivo `runs/<id>/resumo.md`, que fica fora do histórico. A coleta da revisão humana usa só o que o git mostra: depois de um `fetch`, quais commits da execução chegaram à branch principal, identificados por `Task-Id` e `Stage-Id`.

## Consequências

- A tabela de idempotência tem 10 operações; a linha "Criação do PR" saiu.
- Quem revisa abre o PR à mão, com o resumo como texto.
- Comentários do revisor não são lidos automaticamente; podem entrar como um arquivo de texto que o usuário aponta.
- A questão 5 do plano está decidida.

Ver a especificação, seções "Git, worktrees e entrega" e "Coleta da revisão humana".
