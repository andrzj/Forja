# 0025. A rede do E2E é desligada por armadilha de proxy, sem sandbox

## Contexto

A Especificação manda rodar o E2E com a rede desligada, de modo que dependência de serviço real faça o teste falhar, e também manda que a Forja não crie sandbox, com a rede “do ambiente” (ADR 0018) e nenhuma ferramenta dependente de WSL, Linux ou contêiner. As duas ordens só se conciliam com um mecanismo que funcione em qualquer sistema e diga com evidência o que foi tentado.

## Decisão

- **Armadilha de proxy em loopback.** Cada execução de E2E abre um servidor em `127.0.0.1`, porta efêmera, e dá ao processo as variáveis de proxy apontando para ele, mais as chaves de cada ecossistema que medimos serem necessárias (`NODE_USE_ENV_PROXY`, propriedades da JVM em `JAVA_TOOL_OPTIONS`, modo offline de npm, pip e Go). A armadilha registra só `host:porta`, recusa e fecha.
- **Tentativa de rede reprova** o gate mesmo com todos os testes passando.
- **O comando é do repositório** (`[adapters.<linguagem>.commands] e2e`); a Forja não inventa comando. Sem ele o check não executa e o resumo diz.
- **Fakes não são validados.** O resumo registra sempre a premissa de que podem divergir do serviço real.
- **Dados pessoais:** o check `test_data` reaproveita os detectores da redação sobre arquivos de teste e fixture, com catraca por arquivo e tipo.
- **Limite declarado:** cliente que ignora o proxy (soquete cru, Python `http.client`) não é visto. Isto não é contenção; contenção forte é do ambiente.

## Consequências

Funciona no Windows sem privilégio e sem ferramenta extra, e o gate reprova com o destino exato. O custo é a cobertura parcial: quem precisa da garantia forte tem de rodar a Forja já num ambiente sem rede, e a Forja só consegue deixar o limite visível em toda execução. Quando houver o papel que gera fakes, a validação por contrato entra no lugar da premissa fixa. O plano está em `docs/plano-gate-6.md`; o uso, em `docs/e2e-e-dados-de-teste.md`.
