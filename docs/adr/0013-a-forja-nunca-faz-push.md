# 0013. A Forja nunca faz push

- Status: Aceito
- Data: 10/10/2026

## Contexto

O ADR 0001 deixava a Forja enviar a branch da execução ao remoto quando o usuário concedia o push na preparação. Era a única ação da classe "exige concessão". Depois, o usuário decidiu que publicar é tarefa humana: nem a Forja nem o LLM executam push.

## Decisão

Nenhum caminho do código faz `git push`. A fachada restrita recusa o subcomando `push` com a mensagem "Forja never pushes; publishing is for the user", qualquer que seja a branch ou a flag. A ação `PUSH` entra na tabela de autorização como proibida. A classe "exige concessão" e o modelo `Grants` deixam de existir, e o evento de confirmação guarda só o nível de isolamento. A operação de push sai da tabela de idempotência, que fica com 12 operações.

A entrega é a branch da execução, local, mais o `resumo.md`. No fim, a interface e o resumo mostram, como texto, o comando que o usuário pode rodar para publicá-la.

## Consequências

- A preparação não pergunta sobre push, e a Forja não precisa de credencial de remoto.
- Enquanto o usuário não publicar, a branch só existe nesta máquina; o backup do trabalho é dele.
- A coleta da revisão depende de o usuário publicar e de um `fetch`.
- Se uma ação futura precisar de concessão, a classe volta com um ADR próprio.

Ver a especificação, seções "Contrato 3" e "Git, worktrees e entrega".
