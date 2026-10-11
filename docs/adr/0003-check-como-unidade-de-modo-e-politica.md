# 0003. Check como unidade de modo e de política

- Status: Aceito
- Data: 10/10/2026

## Contexto

A especificação definia modo (`bloqueante` ou `observacao`) e política para resultado inconclusivo por gate. Um mesmo gate reúne detectores de maturidade diferente: por exemplo, o gate de voz tem a lista de marcadores de texto gerado por IA, bloqueante por padrão, e o detector de comentário que repete o código, que começa em observação.

## Decisão

A unidade de modo e de política é o *check*, a verificação individual de uma ferramenta ou detector. Um gate agrupa checks. Os gates só julgam evidências; as ferramentas rodam em passos de medição, via adaptadores. A matriz de modo × política para inconclusivo × resultado é validada na carga da configuração, e um check bloqueante sem política para inconclusivo impede o início.

## Consequências

- Um gate pode ter checks em modos diferentes, e a promoção de observação para bloqueante é por check, com data e motivo registrados.
- A configuração e os registros de decisão ganham uma linha por check.
- O glossário da especificação define "Check".

Ver a especificação, seção "Contrato 5: gate".
