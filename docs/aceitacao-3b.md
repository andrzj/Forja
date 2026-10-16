# Aceitação do 3b — mutação, CRAP e métricas opostas

Data: 16/10/2026. Passo 10 do 3b. Os dois casos do "Pronto quando" do `docs\plano-3.md` rodam no pipeline real (`PipelineMeasurer.judge`, coverage.py, lizard e o motor de mutação reais) com o check em questão em `BLOCKING`, como a aceitação pede (os checks nascem em `OBSERVATION`).

## Resultado

| Critério | Evidência | Resultado |
|---|---|---|
| Refatoração que cria método raso é rejeitada mesmo com CRAP melhor | `tests\checks\test_acceptance_3b.py::test_a_split_that_lowers_crap_but_leaves_a_forwarder_is_rejected`: função de CCN 13 totalmente testada vira `_low`, `_high`, `_pick` e `big(n)` que só repassa a `_pick`. `crap` aprova; `pass_through` rejeita `big`; veredito do pipeline: rejeitada | passa |
| Testes de caracterização vazios são rejeitados pela mutação | `test_characterization_tests_that_check_nothing_are_rejected_by_mutation`: o teste congelado executa `add` sem verificar nada; a tentativa troca `a + b` por `b + a`; `mutation` rejeita; veredito: rejeitada | passa |

Execução: 2 passed em 15 s (`FORJA_FAST` não definido; os testes são `slow`).

## O que não está provado

- O passo 9 (validar os medidores contra referência) foi cancelado pelo dono em 16/10. Os limiares de pass-through (repasse puro) e profundidade de módulo (razão 1,0; 10 instruções) são os do plano do passo 8, sem calibração. Os dois checks seguem em `OBSERVATION` por padrão.
- A aceitação cobre Python. Os leitores das outras cinco linguagens são testados em `test_structure.py` e `test_pass_through.py`, não neste arquivo.
- Não houve execução viva com o Claude Code: os dois casos são construídos à mão, como o plano pede ("caso construído de propósito").
- O CRAP do commit pai não é medido (só a função nova ou alterada, ver `plano-3b-passo-7.md`).
- Pendência do 3b: o gate de mutação aprova quando nenhuma linha nova está coberta; cobertura mínima é outro check.
