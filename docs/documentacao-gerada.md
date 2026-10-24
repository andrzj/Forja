# Documentação gerada pela Forja (documentador)

Toda tarefa que altera código termina com uma etapa do **documentador**. Ela vem depois do implementador (e do autor de testes, na correção) e a tarefa só é integrada depois do commit `docs:`. Tarefa que só mexe em documentação não tem documentador.

Os checks desta etapa nascem em **modo observação**: o resultado aparece no resumo, mas só `change_record` e `citations` têm política “bloquear” para o caso de a Forja não conseguir medir. Para promover um check a bloqueante, use a decisão registrada no `forja.toml` descrita em [segurança e dependências](seguranca-e-dependencias.md#promover-para-bloqueio).

## O que fica no repositório

| O quê | Onde | Quem escreve |
| --- | --- | --- |
| Registro de mudança | `docs/mudancas/<tarefa>.md`, no commit `docs:` da tarefa | a **Forja**, não o agente |
| README | o mesmo arquivo, em commit próprio `docs(readme):` antes do commit `docs:` | o agente, só nas seções reprovadas |
| Registro de decisão (ADR) | `docs/adr/NNNN-*.md`, no commit `docs:` | o agente, quando uma regra o exige |

O caminho do registro (`docs/mudancas`) e o dos ADR (`docs/adr`) são fixos. Não há chave de configuração para mudá-los nem para o idioma da documentação.

### Registro de mudança

A parte factual é calculada pela Forja: arquivos e símbolos criados, alterados e removidos (com a prova de não uso de cada remoção, por busca de texto, e a sinalização de remoção de símbolo público), métricas antes e depois, gates aprovados, versões de ferramentas e CLIs, e o commit para reverter. O agente só declara afirmações com citação (`arquivo:linha`, métrica ou fato registrado); a Forja monta a seção “Porquê e impacto” só com as que passaram. Arquivo de registro vindo do agente é sobrescrito.

### README

O README é avaliado sem modelo: existência; seções mínimas (o que é, construir, testar, executar, configurar, dependências, em português ou inglês); comandos de construir e testar iguais, por programa e subcomando, aos que o adaptador executa; links relativos. O agente recebe a lista do que está errado e só pode mexer nessas seções. README aprovado não é tocado. Links externos **não** são conferidos.

### ADR por regra

O detector decide; o agente redige. Dispara com **dependência externa nova** (pelo leitor de manifesto) ou **módulo novo** (diretório com arquivo de produção que a tarefa trouxe e que não existia na base). O gate pede ao menos um ADR novo, com o próximo número livre e as seções de alternativas e de consequências. ADR a mais não reprova. Mudança no grafo entre módulos e em regra de camada ainda não dispara (entra com o gate 9).

## O que os checks leem

| Check | Gate | Reprova |
| --- | --- | --- |
| `change_record` | 14 | registro ausente, sem seção, sem arquivo ou símbolo do diff, ou sem afirmação citada |
| `citations` | 13 | citação de arquivo inexistente ou sem as linhas, de métrica desconhecida ou de fato (hoje nenhum fato é registrado, então citar fato reprova) |
| `readme` | 14 | seção sem problema que mudou; problema que sobrou |
| `doc_drift` | 14 | documento que cita, entre crases, caminho, `make alvo`, `npm\|yarn\|pnpm\|bun run script` ou símbolo que não existem mais |
| `adr` | 14 | gatilho disparado sem ADR novo, numerado e com as seções |
| `voice` | 12 | marcador de texto gerado em documento, comentário ou mensagem de commit; travessões acima de `max_dashes` por arquivo (padrão 3) |
| `comments` | 12 | comentário novo que repete o código; interface pública nova sem comentário |

A deriva (`doc_drift`) tem catraca: só conta citação nova, isto é, que o documento não tinha na base da tarefa ou cujo alvo a tarefa removeu. Só o que está entre crases e fora de bloco de código é lido, e `docs/mudancas/` não é lido. Símbolo existe se cada parte do nome é palavra em algum arquivo que não seja documentação; uma constante ou chave de configuração com o mesmo nome esconde a remoção.

## Ajustar marcadores de voz

A Forja traz uma lista versionada de marcadores (`greeting`, `self-reference`, `inflated`, `announcement`, `offer`, `emoji`). O repositório pode somar os seus e desligar os da Forja no `forja.toml`:

```toml
[voice]
markers_extra = ["\\bsinergia\\b"]   # expressões regulares que o repositório proíbe
markers_off = ["emoji"]              # ids de marcadores da Forja que ele desliga
```

As listas somam entre camadas de configuração. O que o repositório desliga aparece nas notas da preparação, porque afrouxa o gate e quem confirma precisa ver. Id que não existe é ignorado. O limite de travessões muda em `[checks.voice.limits]`, chave `max_dashes`.

## O que o resumo diz

A seção “Documentação” do resumo de entrega lista, por tarefa integrada, o registro, o README e os ADR deixados, e declara o que não foi conferido: links externos do README e o texto que o agente escreveu fora das afirmações com citação (esse só passa pelas verificações de tópico). A seção “Premissas assumidas” traz os checks que não conseguiram medir. O documentador usa a CLI do implementador, sem comandos e só em arquivos de documentação; a preparação e o resumo dizem isso.

## Limites conhecidos

- A Forja não sabe se as linhas citadas dizem o que a afirmação diz: isso é do revisor.
- A prova de remoção de símbolo é busca de texto; nome comum gera homônimo, e na dúvida o registro sinaliza.
- O limite de 75% de palavras repetidas do check `comments` é uma constante, não calibrada com dados de revisão.
- Um arquivo de instrução escrito por pessoa que importe (`@`) um arquivo de `docs/` leva esse texto ao contexto do agente; a Forja não lê esses imports.
