# 0008. Fachada restrita de git e fotografia do repositório

- Status: Aceito
- Data: 10/10/2026

## Contexto

O agente trabalha numa cópia sem `.git`, o que já faz um comando `git` falhar. No nível reduzido de isolamento, porém, um agente que chegue ao repositório principal por caminho absoluto poderia alterar refs, índice, configuração ou hooks, e a retomada partiria de um estado falso.

## Decisão

Toda operação de git da Forja passa por uma fachada restrita (`GuardedGit`) com lista de comandos permitidos e regras para branches protegidas (a padrão do remoto, ou `main`/`master`, mais as configuradas) e para histórico já publicado. Antes e depois de cada chamada ao agente, a Forja fotografa e compara refs, HEAD, branch e índice de cada worktree, `.git/config` e os hooks. Qualquer diferença rejeita a tentativa. No ambiente do agente, `GIT_CEILING_DIRECTORIES` e um `GIT_DIR` inexistente bloqueiam o git por outro caminho, e o ambiente passa por uma lista de variáveis permitidas. Comandos que escrevem usam o mutex de git.

## Consequências

- No nível reduzido, a fotografia é a única defesa nesse caso, e o resumo da execução declara isso.
- Com paralelismo (incremento 7), a fotografia terá de ignorar as refs das outras tarefas.
- Só o push da branch da execução precisa de concessão do usuário; o resto das ações é automático ou proibido.

Ver a especificação, seção "Contrato 3: autorização, isolamento e proteção do git".
