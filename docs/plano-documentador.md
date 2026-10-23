# Plano: incremento 4, o documentador

Estado: plano, nada implementado; sem perguntas abertas. Faz parte da fila obrigatória de `docs\Plano de execução.md` (item 2). **Sem E2E em nenhuma parte** (o dono trata depois); os testes são de unidade e de integração com agentes roteirizados e ferramentas falsas, como nos gates anteriores.

## O que a Especificação e o Plano de execução mandam

- Papel documentador (tabela de papéis): recebe diff, evidências, fatos e premissas; **só escreve** registros de mudança, README e ADR; saída: documentos versionados; gate de saída: citações, deriva, linter de voz, seções mínimas do README.
- Etapa final **obrigatória** de toda tarefa que altera código: a tarefa só é integrada depois do commit `docs:` com o registro de mudança, no mesmo fluxo e integrado junto com o código.
- Registro de mudança: arquivos e símbolos criados, alterados ou removidos (extraídos do diff via tree-sitter), métricas antes e depois, gates aprovados, versões de toolchains e CLIs, premissas, hash para reverter. A parte factual é gerada pela ferramenta; o LLM escreve só o porquê e o impacto, sob verificação de citações. Exclusão exige prova de que o código não é usado; remoção de símbolo público é sinalizada.
- README: avaliação determinística (existência; seções mínimas: o que é, como construir, testar, executar, configurar, dependências; comandos citados iguais aos que o adaptador executou com sucesso; links válidos; símbolos citados existentes); o LLM reescreve só as seções reprovadas; README aprovado não é tocado; commit próprio `docs(readme):`.
- ADR disparado por regra: dependência externa nova, módulo novo, mudança no grafo entre módulos ou em regra de camada; o detector decide, o LLM redige alternativas e trade-offs.
- Deriva: documento existente que cita símbolo, comando ou caminho que deixou de existir reprova.
- Perfil de voz: comentário que repete o código e interface pública sem comentário (observação por padrão); lista versionada e configurável de marcadores de texto gerado; mesmo perfil para comentários, commits e documentação; idioma por repositório.
- Resumo da execução e estrutura do resumo de entrega (item 5, Documentação).
- Tipos de commit não se misturam: `docs:` só toca documentação.
- Pronto quando (Plano de execução): toda tarefa aprovada carrega seu registro; um README com comando de build divergente é detectado e corrigido apenas na seção afetada.

## O que o código tem hoje (lido em 23/10; o passo 0 confere o resto)

- `Producer.DOCUMENTER`, `ArtifactType.CHANGE_RECORD`, `ChangeRecordBody` (arquivos, símbolos, evidências antes e depois, gates aprovados, toolchains, executores, `revert_commit`) em `core\artifacts`; `FileClass.DOCUMENTATION`.
- `TaskCycle.roles()` lê as etapas do plano da tarefa (`stages`); hoje só existem `TEST_AUTHOR` e `IMPLEMENTER`; `_commit_message` só escolhe `test`, `fix`, `refactor`.
- Leitores tree-sitter das seis linguagens em `checks\structure` (forma de função e módulo, para pass-through e profundidade) e `mutation\sites.py`; nenhum extrai símbolos criados, alterados ou removidos.
- Detectores de leitura de manifesto (`languages\*\manifest.py`, `checks\new_dependency.py`) que dizem se uma dependência nova entrou.
- `orchestrator\summary.py` já tem a seção "## Documentação"; `cli\args.py` tem o verbo `documentar` como texto de ajuda do incremento 4 (sem efeito; ver "Não faz parte").
- `docs\adr\` com 24 ADRs numerados.

## Decisões (tiradas da Especificação; as que o texto não fixa estão marcadas e são reversíveis)

1. **Quem escreve o quê.** A Forja gera o registro factual de forma determinística (`change_record`); o documentador (LLM) recebe o registro pronto e escreve só as seções "Porquê" e "Impacto", cada afirmação com citação (`arquivo:linha`, métrica ou fato registrado). O LLM nunca altera a parte factual: o gate recalcula e compara.
2. **Onde fica o registro** (a Especificação não diz o caminho): `docs\mudancas\<task-id>.md`, um arquivo por tarefa, dentro do commit `docs:` da tarefa. Reversível: o caminho é um valor em `forja.toml` (`[documentation] changes_dir`).
3. **Que tarefa tem documentador:** toda tarefa cujo plano altera arquivo de produção ou de teste (`refatorar`, `corrigir`). O planejador acrescenta `DOCUMENTER` como última etapa em `stages`. Tarefa que só mexe em documentação não tem documentador.
4. **Escopo do papel.** O gate de escopo passa a conhecer o documentador: só `FileClass.DOCUMENTATION` (README, `docs\**`, ADR). Arquivo de código, teste, fixture ou configuração reprova (mesma regra dos outros papéis, ao contrário). A classificação de `.md` por adaptador e pelo núcleo é conferida no passo 0.
5. **Commits.** Registro e ADR: `docs:`. README: commit próprio `docs(readme):`. O validador de commits passa a exigir que `docs` só toque documentação (a regra "tipos não se misturam" já vale para os outros).
6. **Gates novos, todos em modo observação ao nascer** (regra geral), com a política de "não consegui medir" indicada: `change_record` (gate 14, `BLOCK`), `doc_drift` (gate 14, `PREMISE`), `readme` (gate 14, `PREMISE`), `citations` (gate 13, `BLOCK`), `voice` (gate 12, `PREMISE`). O gate 13 inteiro (citações de todos os papéis) não é desta etapa: aqui ele confere só a saída do documentador.
7. **Deriva com catraca.** Como nos outros gates (glossário: catraca), reprova só deriva nova em relação à base; documento já divergente não bloqueia toda tarefa. Citam-se entre crases: símbolos, comandos e caminhos; o que não está entre crases não é lido.
8. **Exclusão de símbolo.** A prova de não uso é a busca de referências (texto, nos arquivos rastreados, fora do próprio arquivo apagado). Grafo de chamadas e cobertura que a Especificação também cita ficam para quando houver o gate 9; o registro diz qual prova foi usada. Remoção de símbolo público é sinalizada no registro.
9. **ADR: detectores desta etapa.** Dependência externa nova (leitor de manifesto) e módulo novo (diretório novo com arquivo de produção que antes não existia; unidade = diretório, a mesma do plano do gate 9). Mudança no grafo ou em regra de camada entra junto com o gate 9. Numeração: próximo número livre em `docs\adr\`.
10. **Links do README.** Só os relativos (arquivo e âncora) são conferidos; link externo exigiria rede e fica declarado como não conferido no resumo.
11. **Voz.** Marcadores: lista versionada em arquivo de dados da Forja, ajustável em `forja.toml` (`[voice]`); idioma da documentação por repositório (`[documentation] language`; sem valor, a verificação de idioma não roda e o resumo diz). Comentário que repete o código e interface pública sem comentário: observação, como a Especificação manda; marcadores em comentário, commit e documentação reprovam.
12. **Agente.** O documentador roda como os outros papéis (CLI do papel, cópia sem `.git`, pacote redigido, permissões de arquivo só em documentação, **sem comandos**). Sem CLI própria configurada, usa a do implementador. Premissa do papel (o que assumiu por falta de evidência) vai ao resumo como em qualquer papel.

## Passos (um commit cada; plano antes de código, testar só o que é criado)

0. **Ler e conferir.** Ler por inteiro: as seções da Especificação listadas acima, `core\artifacts` (schemas e store), `orchestrator\task_cycle.py`, `planner.py`, `summary.py`, `checks\scope.py`, `core\gitguard`/validador de `CommitMessage`, `checks\structure`, `agent_runner.py` e o que monta o pacote do papel. Conferir: quem classifica `.md` como `DOCUMENTATION`; como o pacote do implementador e do autor de testes é montado; onde o resumo de entrega lê a seção Documentação; o que a extração de diff por tree-sitter precisa (medir nas seis linguagens com a biblioteca real, num diretório descartável do scratchpad: símbolo criado, alterado, removido, renomeado). Corrigir este plano com o que divergir.
1. **Registro factual determinístico.** `checks\change_record.py`: extrai arquivos e símbolos do diff (tree-sitter, as seis linguagens), junta métricas antes e depois, gates aprovados, versões de toolchains e CLIs, premissas e `revert_commit`; produz `ChangeRecordBody` e o markdown determinístico com as seções "Porquê" e "Impacto" vazias para o LLM. Prova de exclusão por referência (decisão 8). Testes com diffs reais pequenos nas seis linguagens.
2. **Papel no ciclo.** `DOCUMENTER` em `stages` (planejadores), `TaskCycle` (etapa final, `info`, ids de etapa e de tentativa), `CommitMessage` com `docs`, escopo do gate 1 para o documentador, pacote e instruções do papel em `agent_runner`, `RolePermissions` sem comandos. Testes com agente roteirizado: tarefa de refatoração termina com o commit `docs:`; documentador que mexe em código é devolvido.
3. **Gate 14, registro.** `checks\change_record_gate.py`: o registro existe no commit `docs:` e a parte factual é igual à recalculada; "Porquê" e "Impacto" não vazios. Junto, o validador de commits (`docs` só documentação). Spec `change_record` (14, observação, `BLOCK`).
4. **Gate 13, citações do documentador.** `checks\citations.py`: toda afirmação do documentador cita algo que existe e confere (arquivo:linha existe e o intervalo é válido; métrica existe nas evidências da tarefa; fato registrado existe). Sem citação, rejeita. Spec `citations` (13, observação, `BLOCK`).
5. **Gate 12, voz.** `checks\voice.py` e a lista de marcadores como dado versionado: marcadores em comentários e linhas adicionadas, mensagens de commit e documentação reprovam; comentário que repete o código e interface pública sem comentário em observação (comparação de palavras do comentário com identificadores próximos, pelos leitores tree-sitter). Spec `voice` (12, observação, `PREMISE`).
6. **README.** `checks\readme.py`: avaliação determinística (existência, seções mínimas, comandos citados contra os que o adaptador executou com sucesso, links relativos, símbolos citados); o documentador recebe só as seções reprovadas e só elas podem mudar (o gate compara as demais byte a byte); commit `docs(readme):`. Spec `readme` (14, observação, `PREMISE`). Teste do critério do Plano: README com comando de build divergente é detectado e só a seção afetada muda.
7. **Deriva.** `checks\doc_drift.py`: símbolos, comandos e caminhos entre crases em documentos existentes contra a árvore; catraca contra a base. Spec `doc_drift` (14, observação, `PREMISE`).
8. **ADR por regra.** `checks\adr_trigger.py` (dependência nova, módulo novo) e o documentador redigindo o ADR em `docs\adr\` (alternativas e trade-offs, com citações); o gate reprova ADR faltando quando o detector dispara; ADR a mais não reprova. O ADR vai no commit `docs:` da tarefa, junto com o registro.
9. **Resumo.** Seção Documentação do resumo de entrega (registros, README, ADR, o que não foi conferido: links externos), `premissas`/`notices` do documentador, resumo da preparação (CLI do documentador).
10. **Fecho.** Documentação do usuário (`docs\documentacao-gerada.md`: onde ficam os registros, como ajustar marcadores e idioma, o que os gates leem), ADR da decisão 2 e 5, gate de mutação no WSL nos arquivos novos (como nos gates anteriores), atualização de `docs\Plano de execução.md` (registro de andamento). Critério de pronto do Plano: tarefa aprovada carrega seu registro; README com comando divergente corrigido só na seção afetada.

## Não faz parte

- E2E de qualquer tipo (do dono).
- O verbo `forja documentar` ("entende o código e escreve a documentação"): depende do arqueólogo (incremento 6); continua só como texto de ajuda.
- Gate 13 para os outros papéis (arqueólogo, especificador): entra com eles.
- Gatilhos de ADR por grafo e camada: entram com o gate 9.
- Prova de exclusão por grafo de chamadas e cobertura; links externos do README.
- Geração do ADR ou README sem LLM; LLM aprovando qualquer gate.

## Limites já conhecidos

- O detector de símbolos por diff acha declarações, não prova uso; a prova de exclusão por busca de referências erra por nome comum (homônimos): o registro diz o método e a sinalização é conservadora (na dúvida, sinaliza).
- A deriva só lê o que está entre crases.
