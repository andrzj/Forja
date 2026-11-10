# Duplicação (check `duplication`, gate 8)

O check `duplication` reprova a tentativa que acrescenta código repetido a um arquivo de produção. Quem mede é o `jscpd`. O check pertence ao gate 8 (métricas), junto de `complexity`, `crap`, `pass_through` e `module_depth`, e começa em modo observação: mede e reporta, mas não reprova até o repositório promovê-lo. O índice dos gates está em `README.md`; a política do repositório, em `..\forja-toml.md`.

## O que mede

| Ponto | Comportamento |
| --- | --- |
| Só duplicação nova | O `jscpd` recebe o commit contra o qual o trabalho é lido e marca cada clone como novo quando o conteúdo do fragmento não existe naquele commit. O conteúdo é identificado por hash: mover o arquivo ou deslocar linhas não torna um clone antigo em novo. |
| Só em arquivo de produção que a tentativa mudou | Um clone novo com pelo menos um lado em arquivo de produção alterado vira achado. Duplicação antiga, ou nova só entre arquivos que a tentativa não tocou, não reprova. |
| Sem arquivo de produção alterado | O check aprova sem rodar o `jscpd`. |
| Testes ficam de fora | Todos os arquivos de teste do repositório (rastreados) e os de teste que a tentativa mudou entram na lista de ignorados. Repetir preparação de teste é comum; a regra é sobre código de produção. |
| Texto repetido, não intenção | Duas abstrações diferentes que fazem a mesma coisa passam. |

Esta é uma catraca: o passivo que o repositório já tem não impede uma melhoria alheia. Quem acrescenta uma cópia nova, mesmo de um trecho que já era duplicado, é reprovado, porque uma cópia a mais não existia no commit de comparação.

Cada lado de um clone novo que está em arquivo de produção alterado gera um achado. Um clone entre dois arquivos alterados gera dois achados. O achado traz o arquivo, a linha em que o trecho começa, o tamanho do clone em linhas e o outro lado, na forma `N duplicated lines, also in outro/arquivo.py:42`.

## Chaves e padrões

O check aceita só `mode`, `on_inconclusive`, `promotion` (veja `..\forja-toml.md`) e dois limites, que valem para o repositório inteiro. Não há limiar por linguagem.

| Chave | Padrão | Valor usado | Efeito |
| --- | --- | --- | --- |
| `limits.min_tokens` | `50` | inteiro | tamanho mínimo, em tokens, de um trecho repetido para contar como clone |
| `limits.min_lines` | `5` | inteiro | tamanho mínimo, em linhas, de um trecho repetido para contar como clone |
| `mode` | `observation` | `observation` ou `blocking` | com `blocking`, achado reprova a tentativa |
| `on_inconclusive` | `premise` | `block` ou `premise` | o que fazer quando o `jscpd` não deu resposta |

O arquivo aceita só número inteiro, zero ou mais, em `min_tokens` e `min_lines`. Um valor com parte decimal, como `40.5`, é recusado na leitura com o erro `must be a whole number`. Os valores são passados ao `jscpd` por um arquivo de configuração gerado pela Forja, e por isso a configuração do próprio repositório para o `jscpd` (`.jscpd.json`, chave `jscpd` do `package.json`) não vale.

## Linguagens

O check não tem tabela por linguagem. Ele não filtra por tipo de arquivo: lê os arquivos de produção alterados, qualquer que seja a linguagem, e quem decide se um formato é lido é o `jscpd`. O que conta como arquivo de teste vem da classificação de cada adaptador de linguagem, a mesma dos outros gates.

## O que acontece ao falhar

| Resultado | Em observação | Em bloqueio |
| --- | --- | --- |
| Sem achado | passa | passa |
| Com achado | aparece no relatório | reprova a tentativa; o motivo vai para a próxima tentativa |
| Inconclusivo | aparece no relatório | com `on_inconclusive = "premise"` (padrão), segue e declara a lacuna como suposição; com `"block"`, bloqueia a tarefa |

Falha da ferramenta nunca aprova. Resultado inconclusivo vem de: `jscpd` que não inicia ou não é encontrado, saída diferente de 0, relatório ausente, velho ou ilegível. A Forja não liga nenhuma porta de saída do `jscpd` (como `--threshold`), então saída diferente de 0 é sempre falha da ferramenta, nunca um veredito.

A semântica completa de `mode` e `on_inconclusive` está em `..\forja-toml.md`.

## O que o agente recebe

O agente que escreve código recebe, no pacote da tarefa, uma seção `## Duplication`, com texto fixo da Forja e os valores de `min_lines` e `min_tokens` da política do repositório. Assim o aviso e a medição concordam. O texto, em inglês, diz ao agente:

- que um trecho de `min_lines` linhas ou `min_tokens` tokens igual a outro do repositório é um clone, e que o check rejeita o clone acrescentado a um arquivo de produção;
- que deve procurar um bloco que já faça o trabalho e chamá-lo, antes de escrever outro;
- que, se a mesma lógica for necessária em dois lugares, deve pô-la numa função ou módulo e chamá-la dos dois;
- que copiar e trocar um nome ou número continua sendo clone: o que difere vira parâmetro;
- que duplicação que já existia não é dele para consertar, salvo se a tarefa pedir;
- que testes podem repetir preparação, e que a regra é sobre código de produção;
- que um fato do dono pode pedir uma cópia, e que a regra continua valendo: ele não deve esconder o clone mudando a estrutura para o check passar, deve escrever a cópia pedida e, se o check a rejeitar, deixá-la como está e declarar em `assumptions` que o fato e a regra entram em conflito, com o id do fato. A tarefa pode então terminar bloqueada em vez de entregue por contorno.

Recebem a seção o implementador e a correção. Autor de testes, documentador, especificador e arqueólogo não a recebem. Quando o check reprova, o agente vê o achado (arquivo, linha e o outro lado) na tentativa seguinte, como nos outros gates.

## Promover para bloqueio

O check nasce em observação. Para que um achado passe a reprovar a tentativa, mude `mode` para `blocking` e registre a decisão em `promotion`. Os passos, as regras e as mensagens de erro estão em `seguranca-e-dependencias.md#promover-para-bloqueio`.

## Exemplos

Limites mais sensíveis, para pegar trechos menores:

```toml
# Trechos a partir de 40 tokens e 4 linhas já contam como clone.
# O agente recebe os mesmos números na instrução.
[checks.duplication.limits]
min_tokens = 40
min_lines = 4
```

Promoção a bloqueio:

```toml
# O check nasce em observação. Para bloquear, a promoção exige data e motivo.
[checks.duplication]
mode = "blocking"
on_inconclusive = "premise"   # se o jscpd não rodar, segue com a lacuna declarada como suposição
promotion = { date = 2030-01-31, reason = "o repositório passou a ser medido sem clones novos" }

# Os limites podem vir na mesma seção de limites; sem eles, valem 50 tokens e 5 linhas.
[checks.duplication.limits]
min_tokens = 60
min_lines = 6
```

Bloqueio que trava a tarefa quando o `jscpd` falha:

```toml
# Sem resposta da ferramenta, a tarefa para, em vez de seguir com a lacuna.
[checks.duplication]
mode = "blocking"
on_inconclusive = "block"
promotion = { date = 2030-02-15, reason = "o jscpd roda em todas as máquinas do time" }
```

## Instalar o `jscpd`

O `jscpd` é obrigatório no `forja doctor`. A Forja o instala com `forja instalar` na pasta de ferramentas dela, sem mexer no `PATH` do sistema; um `jscpd` já no `PATH` vale e não é baixado de novo. O binário é autossuficiente e não precisa de Node. Há pacote para Windows x64 e Linux x64. O `git` precisa estar presente, porque a comparação com o commit pai depende dele. Detalhes em `..\instalacao.md` e, para o comando, em `..\comandos.md`.

## Limites

- **A tentativa pode esconder clone.** O `jscpd` respeita `.gitignore`, `.ignore` e as regiões marcadas com `jscpd:ignore-start` e `jscpd:ignore-end`. Um agente que acrescenta uma dessas marcas esconde o clone da medida. A Forja não desliga o `.gitignore`, porque isso varreria dependências e ambientes virtuais. A revisão do ramo é o que pega esse caso.
- **Só o que o `jscpd` enxerga.** Um clone que o `jscpd` não detecta não aparece, e o check não mede intenção.
- **Duplicação antiga não reprova.** Ela é dívida do repositório, não da tentativa.
