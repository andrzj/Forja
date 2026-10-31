# Mutação incremental

O gate de mutação roda o mutator da Forja (ADR 0021) sobre o código que a tentativa tocou. Este documento diz quais mutantes entram, o que reprova, o que a Forja não guarda entre tentativas, e por que nenhum adaptador de linguagem declara a capacidade `MUTATION_INCREMENTAL`.

## O que muda

Antes, o gate mutava só as linhas que a tentativa adicionou. Agora ele muta a **função inteira** de cada função que a tentativa tocou: se uma linha adicionada cai dentro de uma função, todos os sítios de mutação dessa função entram, não só os da linha nova.

- `checks\mutation.py::touched_functions` acha as funções que contêm alguma linha adicionada. Os trechos de cada função vêm de `mutation\sites.py::function_spans`.
- `checks\mutation.py::build_mutants(..., whole_functions=True)` é o padrão: monta um mutante para cada sítio das linhas adicionadas e, além disso, para cada sítio dentro das funções tocadas.

A referência é o modo diferencial do `unclebob/mutator`: ele reexecuta todo sítio de uma função cujo texto mudou, e um mutante morto em função não alterada continua morto. Ele guarda esse estado num snapshot; a Forja não guarda (ver abaixo).

## Quais regras reprovam

- **Linha adicionada sem cobertura.** Continua reprovando: nenhum teste roda a linha nova, e a tentativa precisa de teste antes da mutação (`UNTESTED_LINE`).
- **Linha antiga sem cobertura em função alterada.** Não reprova. O mutante dessa linha não roda, e fica fora da nota. Só as linhas que a tentativa escreveu são cobradas por falta de teste.
- **Linha antiga coberta em função alterada.** O mutante roda como qualquer outro. Se sobreviver, entra na nota e pode reprovar pelo `min_score` da linguagem.

## Sem snapshot entre tentativas

A Forja não guarda o resultado de mutação de uma tentativa para a seguinte. Cada tentativa vale por si, com as funções que ela mudou. Um sobrevivente que já existia numa função que a tentativa não tocou não é cobrado. A regra segue a ideia de catraca, não de faxina: o gate cobra o que a tentativa mexeu, não a dívida antiga.

## Limites e custo

- **Custo maior.** Uma tentativa roda todos os sítios das funções que tocou, e não só os das linhas novas. Em função grande, são muitos mutantes a mais.
- **Função aninhada e a que a envolve mudam juntas.** A função de fora tem como trecho as linhas da de dentro. Mexer numa das duas põe as duas no conjunto.
- **Sobrecargas com o mesmo nome qualificado mudam juntas.** O conjunto é escolhido pelo nome da função, então duas definições com o mesmo nome qualificado entram juntas.

## Por que nenhum adaptador declara `MUTATION_INCREMENTAL`

`core\adapters\language.py` define `LanguageCapability.MUTATION_INCREMENTAL`, e `OperationRequest` tem o campo `incremental`. Nenhum adaptador de linguagem declara a capacidade, e o check não a consome. O motivo:

- O contrato de conformidade (`tests\core\adapters\conformance.py`, linhas 195 a 199) diz que um adaptador que declara `MUTATION_INCREMENTAL` precisa planejar um comando de mutação incremental, e que sem a capacidade um pedido incremental deve ser `NotSupported`.
- Nenhum adaptador planeja um comando de mutação. A mutação é do mutator da Forja (ADR 0021), não de cada linguagem. A única ligação entre `MUTATION` e a operação está no mapeamento de `language.py`.
- Declarar a capacidade exigiria inventar, para cada adaptador, um comando de mutação que não existe. Por isso nenhum declara.

A decisão está em [ADR 0034](adr/0034-a-mutacao-muta-a-funcao-inteira-sem-capacidade-incremental.md).
