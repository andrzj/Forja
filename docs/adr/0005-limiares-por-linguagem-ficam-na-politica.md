# 0005. Limiares por linguagem ficam na política

- Status: Aceito
- Data: 10/10/2026

## Contexto

A especificação listava os limiares calibrados por linguagem no contrato do adaptador, mas também dizia que o TOML configura "limiares por linguagem". Os dois lugares se contradiziam, e o adaptador, que só descreve e interpreta (ADR 0004), não deve carregar números de calibração.

## Decisão

Os limiares ficam na política. A política tem camadas TOML, da menos para a mais específica: padrões do código, configuração do usuário, `forja.toml` do repositório e arquivo da execução. A carga valida tudo e junta todos os problemas numa só mensagem. Promover um check de observação para bloqueante exige `{date, reason}`. A política vigente é congelada em `policy.json` na execução, e sua versão é `<versão da Forja>+<12 hex>`.

## Consequências

- Mudança de limiar é rastreável pela versão da política, registrada em cada decisão de gate.
- Os valores iniciais por linguagem continuam em aberto (questão 1 do plano).
- Os nomes de arquivo `forja.toml` e do arquivo de execução ainda precisam de confirmação no incremento 1.

Ver a especificação, seção "Contrato 5: gate", parágrafo "Políticas e configuração".
