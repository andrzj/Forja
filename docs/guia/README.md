# Guia da Forja

Documentação de uso. Cada página tem exemplos comentados de todo comando, argumento, configuração e arquivo de configuração que ela cobre.

## Para começar

| Página | O que responde |
| --- | --- |
| [Instalação](instalacao.md) | Como instalar a Forja, o que `forja doctor` confere, o que `forja instalar` traz, o que fica por sua conta, por plataforma. |
| [Comandos](comandos.md) | Todos os comandos e argumentos de `forja`, com exemplo de cada um. |
| [Ambiente](ambiente.md) | Variáveis de ambiente, pastas e arquivos que a Forja cria, teclas e temas da tela. |

## Configuração

| Página | O que responde |
| --- | --- |
| [execucao.toml e modo CI](execucao-toml.md) | Cada chave do `execucao.toml`; rodar sem perguntas com `--config`. |
| [forja.toml](forja-toml.md) | A política do repositório: modo de cada gate, limiares e comandos. |
| [CLIs de agente](clis.md) | Escolher a CLI de cada papel, autor de testes separado, adaptador genérico `[clis.<nome>]`. |

## Gates

| Página | O que responde |
| --- | --- |
| [Visão geral dos gates](gates/README.md) | Os 14 gates, o modo de cada um e o que cada resultado significa. |
| [Segredos e segurança](gates/seguranca-e-dependencias.md) | Gates 2 e 10: segredos, SAST, auditoria e licenças de dependências. |
| [Formato, lint e tipos](gates/tipos.md) | Gate 3 e o check de tipos. |
| [Testes, e2e e dados de teste](gates/e2e-e-dados-de-teste.md) | Gates 5 e 6. |
| [Mutação e métricas](gates/mutacao.md) | Gates 7 e 8. |
| [Duplicação](gates/duplicacao.md) | O check `duplication`. |
| [Arquitetura e dependências](gates/arquitetura-e-dependencias.md) | Gate 9: ciclos, camadas e métricas de pacote. |
| [Teste diferencial](gates/teste-diferencial.md) | Gate 11. |
| [Teste de propriedades](gates/teste-de-propriedades.md) | O check `properties`. |

## Durante e depois da execução

| Página | O que responde |
| --- | --- |
| [Documentação gerada](documentacao-gerada.md) | O que a Forja escreve no repositório, quando, e a voz dos textos. |
| [Diário de bordo](diario-de-bordo.md) | O histórico das tentativas que o agente vê e que acompanha a entrega. |
| [Paralelismo](paralelismo.md) | Rodar tarefas ao mesmo tempo, o que acontece num conflito de integração e os limites. |
