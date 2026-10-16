# 0021. A mutação das seis linguagens segue o unclebob/mutator

## Contexto

A ADR 0020 manteve um motor próprio para Python e deixou PIT, gremlins e Stryker para as outras
linguagens. Isso criou um motor só de Python, leitores de três formatos de relatório que nenhuma
linguagem usava ainda e um passo de calibração contra ferramentas de referência. O dono definiu que
a referência é o `unclebob/mutator`, que já cobre Java, Go, TypeScript/JavaScript e Python com uma só
tabela de regras sobre tree-sitter, e que as referências indicadas são seguidas como estão
(`CLAUDE.md`).

## Decisão

- Os sítios de mutação vêm das regras do mutator, portadas para `src/forja/mutation/sites.py` sobre
  tree-sitter. Medido contra o `_visit` original sobre `src` e `tests` da Forja: nenhuma diferença.
- C# não existe no mutator; segue o conjunto de Java, com o nó unário do C# acrescentado.
- Cada mutante roda o comando de testes inteiro. O mutante morre quando os testes falham ou estouram
  o tempo (10 vezes o baseline, no mínimo 2 s). Linha sem cobertura não é mutada.
- A nota é mortos / (mortos + sobreviventes); linha sem cobertura fica fora.
- Os leitores de PIT, gremlins e Stryker foram removidos. A Especificação não nomeia mais
  ferramenta de mutação por linguagem.
- Fica de fora o que o mutator faz por causa do Unix: links simbólicos e `killpg`. A Forja copia a
  árvore para cada worker.

## Consequências

A ADR 0020 está substituída. Não há passo de calibração contra ferramenta de referência para a
mutação: a referência é o próprio mutator. O gate de mutação aprova quando nenhuma linha nova está
coberta; exigir cobertura mínima é assunto de outro check.
