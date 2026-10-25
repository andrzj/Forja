# Plano: gate 11, teste diferencial

Estado: plano, nada implementado, **sem perguntas abertas**. **Adiado pelo dono (23/10): a construção só começa depois do gate 6 (E2E com fakes e rede desligada) e do autor de testes com o `manifesto-testes.json`**, porque os casos vêm dos geradores e fakes dos E2E, como a Especificação manda. Regra do dono: gates grandes só com plano escrito antes.

## O que a Especificação diz

- Tabela de gates, linha 11: reprova quando as **saídas da versão nova diferem da antiga para as mesmas entradas, em tarefa de refatoração**, ou há **regressão de tempo ou memória acima do limite**.
- Seção "Teste diferencial": em refatoração e modernização, versão antiga e nova executam as mesmas **entradas sintéticas**; as saídas (arquivos, tabelas, eventos) são comparadas **byte a byte ou por regra declarada**. O mesmo mecanismo mede **tempo, memória e I/O** antes e depois, como gate de custo operacional para jobs batch. **Usa os mesmos geradores e fakes dos E2E.**
- Seção "Onde o código do repositório executa": o teste diferencial executa código do repositório (não confiável), no ambiente do usuário, como build e testes.
- Plano de execução, incremento 5: "teste diferencial com medição de tempo e memória", junto do "E2E com fakes e rede desligada" (gate 6).
- Regras gerais que valem aqui: check novo nasce em **modo observação**; ferramenta que falha é `Inconclusive`, nunca aprovação; configuração do repositório prevalece sobre o padrão; o que o usuário deve fornecer e não foi fornecido **não executa e o resumo diz isso** (ADR 0024).
- Esquema que já existe (`core/artifacts/schemas.py`): `DataGenerator(name, seed, path)` em `AuthoredTestsBody.generators`, parte do `manifesto-testes.json` do autor de testes (papel do incremento 6). Nenhum adaptador implementa `Operation.E2E`; nenhum código executa geradores.

## O que o código tem hoje (lido em 23/10)

- `ProcessResult` traz `outcome`, `exit_code`, `duration` e `log_path`; **não traz memória nem I/O**. No Windows o Job Object já declara os campos `PeakProcessMemoryUsed` e `PeakJobMemoryUsed` na estrutura (`process/_windows.py`), mas nada os lê. O ramo POSIX existe e não foi exercitado em produção.
- `Operation.E2E` e `LanguageCapability.E2E` existem; os cinco adaptadores não os implementam.
- O estado antigo de uma tentativa já é reproduzível: `checks/oldtree.py::old_tree` devolve uma cópia privada da worktree com os textos do commit pai; `PipelineMeasurer.baseline()` mede a base uma vez por execução e grava `base.json`.
- O objetivo da execução (`Objective.REFACTOR` ou `FIX`) está em `RunConfig`; o gate só vale para refatoração.

## Decidido pelo dono (23/10)

1. **Casos:** esperar o gate 6 e o autor de testes. Os casos vêm dos geradores e fakes dos E2E (`DataGenerator` e `manifesto-testes.json`); **não há arquivo de casos escrito à mão pelo usuário**, e nada é construído antes.
2. **Versão antiga:** construída e executada **na medição da base**, uma vez por execução, e guardada; cada tentativa só roda a versão nova e compara.
3. **Limites iniciais:** 3 execuções, mediana, razão máxima 1,25 para tempo e para memória; valores por linguagem em `thresholds` (`max_time_ratio`, `max_memory_ratio`, `runs`), em modo observação, a calibrar.
4. **I/O:** fica fora por ora; o resumo e a documentação o registram como limite conhecido.

## Decisões do plano

1. **Um check, `differential`**, gate 11, `Mode.OBSERVATION`, política para “não consegui medir”: `PREMISE` (a decidir junto com a pergunta 3). Só roda quando `RunConfig.objective` é refatoração; em correção devolve `NotApplicable` (o comportamento muda de propósito).
2. **Casos do manifesto de testes** (depois do gate 6 e do autor de testes): cada caso declara nome, comando exato (lista de argumentos, sem shell), semente do gerador ou arquivo de entrada, o que comparar (saída padrão, código de saída, arquivos gerados) e a regra de comparação (`bytes`, `json` canônico ou `ignorar` com padrões declarados). Os casos são lidos do **commit em que o autor de testes os congelou**, fora da worktree do implementador, que não pode editá-los para silenciar uma diferença. Sem casos: `NotApplicable`, e o resumo da preparação e o da entrega dizem em destaque **“Teste diferencial não executado: sem casos”**. O formato exato sai do esquema do `manifesto-testes.json` quando ele for definido; este plano não o fixa antes.
3. **A versão antiga** é construída e executada **na medição da base**, uma vez por execução; as saídas e as medidas ficam em `base.json` (ou arquivo vizinho). Cada caso roda **duas vezes** na base: se as saídas diferem, o caso é não determinístico e vai para quarentena como evidência (o mesmo critério da suíte instável), nunca reprova a tentativa.
4. **Medição.** Tempo vem de `ProcessResult.duration`. Memória exige expor o que o runner já tem ou pode ter: pico do Job Object no Windows, `ru_maxrss` dos filhos no POSIX (documentação a ler no passo 0). **I/O fica fora.** Regressão = mediana das 3 execuções novas acima de 1,25 × a mediana da base; a razão e o número de execuções são valores da política, por linguagem.
5. **Segurança de execução.** O comando do caso roda pelo mesmo caminho que build e testes (`Tools.run`, ambiente filtrado, sem rede quando o isolamento permitir); os arquivos de saída são lidos de um diretório fora da worktree.
6. **Nada de comparação inventada:** só as regras que o caso declara. Diferença sem regra declarada é diferença.

## Passos (um commit cada)

**Pré-requisitos (fora deste plano):** gate 6 (E2E com fakes e rede desligada) e o papel autor de testes com `manifesto-testes.json` (incrementos 5 e 6). O passo 2 abaixo (medida de memória no runner) não depende deles e pode ser feito antes, se o dono quiser.

0. **Ler o que falta:** a documentação do Windows para `JOBOBJECT_EXTENDED_LIMIT_INFORMATION` (pico de memória do Job Object); a documentação do Python para `resource.getrusage` e `subprocess`; como o runner atual cria o Job Object; o esquema do `manifesto-testes.json` que o gate 6 e o autor de testes tiverem definido. Corrigir este plano se algo divergir.
1. **Modelo e leitura dos casos** (do manifesto de testes): validação, recusa de comando com shell, leitura do commit congelado, cópia fora da worktree, `NotApplicable` sem casos. ADR (o teste diferencial só executa com casos do manifesto; sem eles não executa). Linha no resumo da preparação e da entrega (`security_notes`-like).
2. **Medida de memória no runner:** pico de memória em `ProcessResult`, com teste nos dois ramos que se puder exercitar; plataforma sem medida devolve `None`, nunca zero.
3. **Executor de caso:** roda o comando, captura saída padrão, código de saída e arquivos declarados num diretório fora da worktree, mede tempo e memória; falha da ferramenta é `Inconclusive`.
4. **Comparação:** `bytes`, `json` canônico, `ignorar` com padrões; relatório de diferença curto (primeira divergência e tamanho), sem copiar conteúdo sensível para a mensagem.
5. **Base:** construção e execução da versão antiga na medição da base, duas execuções por caso, quarentena de caso instável, gravação das saídas e medidas.
6. **`DifferentialCheck`:** compara a versão nova com a base (saídas e razão de tempo/memória por mediana de 3 execuções, razão 1,25), `CheckSpec` com `thresholds={"max_time_ratio","max_memory_ratio","runs"}`, só em refatoração.
7. **Integração:** registro no `PipelineMeasurer.judge` depois de `new_dependency`, avisos (`notices`), resumo da preparação, política.
8. **Documentação do usuário:** de onde vêm os casos, regras de comparação, limites, o que não é medido (I/O e plataformas sem medida de memória).
9. **Ponta a ponta real** com um repositório de exemplo por linguagem (regra do dono: testes reais só no fecho) e **gate de mutação (`scripts/mutate.py`)** nos arquivos novos.

## Limites já conhecidos

- Sem os geradores e fakes dos E2E (gate 6) e o autor de testes, não há casos e o check não executa (decisão do dono).
- A comparação só vale para saídas determinísticas; o que não é determinístico precisa de regra declarada ou fica em quarentena.
- Tempo e memória variam com a máquina; por isso mediana de várias execuções, razão em vez de valor absoluto e modo observação até haver dados.
- Em POSIX o ramo do runner não foi exercitado em produção; a medida de memória lá só se verifica no gate de mutação (`scripts/mutate.py`) e no ponta a ponta.
