# Regras da construção da Forja

Mandam sobre qualquer plano ou nota anterior.

1. **Referências do dono são a especificação.** Repositórios e bibliografia que o dono indicou são seguidos como estão. Não reinterpretar, "inspirar-se em" nem reescrever. Para mutação: o comportamento é o de `unclebob/mutator`, e a expansão para outras linguagens segue o modo como o próprio mutator permite expandir.
2. **Ler a referência por inteiro antes de implementar.** Nada de construir a partir de leitura parcial.
3. **Não inventar escopo.** Sem calibração extra, validação extra, leitores, formatos ou linguagens que ninguém pediu. Fazer só o que a Especificação e o dono pediram.
4. **Não inventar perguntas.** Perguntar só quando a Especificação e as referências não respondem. Caso contrário, decidir e seguir.
5. **Sem rodeios.** Sem retomar o que já foi decidido, sem listar alternativas que não serão feitas. Menos sessões, menos custo.
6. **`NOTAS.md` manda no que fazer.** Antes de qualquer demanda, ler `NOTAS.md` inteiro: é a fonte única do que está comprometido, aberto e do dono. Trabalhar só no que o dono mandar ou no compromisso da seção 1, na ordem dela; não escolher, não antecipar, não acrescentar. Todo andamento (item feito, decisão, item novo) é registrado em `NOTAS.md` antes do commit, com numeração estável e conferido no código.
