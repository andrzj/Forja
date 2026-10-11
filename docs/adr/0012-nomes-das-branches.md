# 0012. Nomes das branches da execução e da tarefa

- Status: Aceito
- Data: 10/10/2026

## Contexto

A branch da tarefa chama-se `forja/<execução>/<tarefa>`. A branch da execução não podia ser `forja/<execução>`: o git não aceita um ref e um diretório de refs com o mesmo nome, e a criação da branch da tarefa falha. A especificação não fixava nenhum dos dois nomes; o conflito apareceu no teste de retomada.

## Decisão

A branch da execução é `forja-run/<execução>` e a da tarefa é `forja/<execução>/<tarefa>`. A alternativa, inverter para `forja/<execução>` e `forja-task/<execução>/<tarefa>`, foi descartada porque exigia mexer no reconciliador e nos testes.

## Consequências

- Os dois prefixos ficam fáceis de listar e de proteger separadamente.
- O nome `forja-run` entra na documentação do usuário quando houver uma.

Ver a especificação, seção "Worktrees".
