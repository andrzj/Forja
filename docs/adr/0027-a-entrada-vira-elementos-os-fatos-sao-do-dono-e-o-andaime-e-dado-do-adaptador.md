# 0027. A entrada vira elementos, os fatos são do dono e o andaime é dado do adaptador

## Contexto

A Especificação manda que cada elemento da entrada vire critério e que nenhum critério fique sem origem; que premissa confirmada ou corrigida por pessoa vire fato registrado e entre nos pacotes futuros; e que a criação a partir de ideia use um andaime determinístico num diretório vazio. Não diz como segmentar a entrada, em que formato e onde guardar os fatos, nem onde o andaime entra no fluxo.

## Decisão

- **Elementos (decisão 4 do plano).** Antes de chamar o especificador, a Forja corta a entrada em elementos com id estável (`E1`, `E2`…): um por item de lista e um por parágrafo; título sozinho não conta. `Criterion.origin` é a lista de ids de onde o critério veio. O check `traceability` aponta elemento sem critério, critério com origem inexistente e elemento deixado de fora que não existe. Elemento que o especificador declara fora do que será construído exige premissa com motivo e não reprova. O check nasce em observação.
- **Fatos (decisão 9).** O fato é uma linha de um arquivo de texto que o dono mantém e aponta (`--fatos` ou `fatos` no `execucao.toml`): `id | autor | data | texto [| confirma:<premissa> | corrige:<premissa>]`. Linha malformada recusa a execução. Os fatos entram em `RunConfig.facts`, no pacote de todo papel e em `fact_ids` do gate 13. **A Forja não os guarda entre execuções** (divergência da decisão 9 do plano, que pedia guardá-los por hash no diretório de dados): o arquivo do dono é a fonte única e não há cópia que possa divergir dele. A coleta da revisão lê o mesmo formato.
- **Andaime (decisão 11).** Cada adaptador de linguagem declara `template(name)`, um `ProjectTemplate(files, setup)`: manifesto, estrutura de código e de testes, `.gitignore`, `.gitattributes` e um teste que passa. Nada vem de modelo de linguagem. O andaime (`git init`, commit `chore: scaffold …`, `setup` do modelo) **roda depois da confirmação**, não antes, como previa o plano: um “não” ou `--plano` não pode ter escrito no diretório do dono. A medição de que build e testes do modelo passam é a linha de base da própria execução. Cinco linguagens; JavaScript fica sem modelo porque o adaptador do TypeScript só vê projeto com `tsconfig.json`.

## Alternativas

- *Perguntar ao especificador quais são os elementos.* Tira da Forja a garantia de que nada foi esquecido: o modelo decidiria o que conta como elemento.
- *Segmentar por frase.* Mais fino, mas parte critérios que dependem de duas frases e aumenta a lista que a revisão confere.
- *Guardar os fatos por hash no diretório de dados.* Dá memória entre execuções, ao custo de uma segunda fonte que pode contradizer o arquivo do dono. Reversível quando o dono pedir.
- *Andaime antes do “sim”.* Deixaria o diretório alterado depois de uma recusa.
- *Modelo de projeto gerado por LLM.* Contraria a regra de que modelo de linguagem nunca aprova nem produz o que o gate mede.

## Consequências

A rastreabilidade é verificável por máquina, mas só tão fina quanto a segmentação: prosa corrida vira poucos elementos grandes, e que o critério diga o que o elemento diz continua sendo da revisão. O dono carrega o arquivo de fatos de uma execução à outra. O andaime precisa de rede para `npm install` e para baixar dependências de Java e C#, e um `setup` que falha deixa o projeto criado e comitado. O uso está em `docs/especificar-e-investigar.md`; o plano, em `docs/plano-especificador-arqueologo.md`.
