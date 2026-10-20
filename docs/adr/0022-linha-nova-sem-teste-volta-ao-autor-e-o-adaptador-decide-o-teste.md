# 0022. Linha nova sem teste volta ao autor; o adaptador decide o que é teste; o lint antigo roda numa cópia

## Contexto

O 3a congelava os testes por diretório e a mutação só reprovava linha nova coberta. Ao generalizar o
pipeline para todas as linguagens (`plano-pipeline-todas-linguagens.md`), três pontos exigiram
decisão: o que fazer com linha nova que nenhum teste roda, como saber que um arquivo e um id de
teste são de teste fora do Python, e como medir o lint do commit pai quando o linter precisa dos
arquivos vizinhos.

## Decisão

- **Estágio extra do autor de testes** (`23f4b30`): linha nova sem teste volta ao autor de testes
  num estágio `<tarefa>-t<n>`, que julga o código commitado e os testes novos juntos, mutação
  incluída. Esse estágio só acrescenta: o `AppendOnlyCheck` (`f5065e4`) reprova alterar, mover ou
  apagar um arquivo de teste que já existia; arquivo novo e mudança em produção passam.
- **O adaptador decide** (decisão do dono, 20/10): `RedGreenCheck` pergunta ao adaptador que
  reivindica o arquivo se o id de teste lhe pertence (`owns_test`, opcional, fora do `Protocol`).
  Python exige `caminho::nome`; Go, TypeScript, C# e Java devolvem `True`, porque o id do runner não
  traz o caminho. O id ainda precisa falhar de verdade na execução e o arquivo precisa ser de
  teste; só o vínculo id-arquivo fica frouxo.
- **Congelamento por arquivo** (`ab71ff0`): o digest cobre os arquivos sob `test_root` (quando há)
  mais os que os adaptadores classificam `TEST` ou `FIXTURE`.
- **Lint do commit pai** (`d668f2f`, `52fe0d5`): roda numa cópia da worktree devolvida ao commit
  pai (arquivos adicionados ou renomeados apagados, textos antigos escritos). A cópia deixa de fora
  `.git` e qualquer link ou junção, para que escrever os textos antigos não saia da cópia. Se o
  linter roda nos arquivos novos e não nos antigos, o resultado é `Inconclusive`, nunca aprovação.

## Consequências

- Checar o id por linguagem (Go por `func TestX`, Java e C# por classe, TypeScript por nome)
  poderia reprovar subtestes e nomes com parâmetros; fica como tarefa própria.
- A cópia inteira da worktree por tentativa custa em repositório grande. Aceito.
- O digest de congelamento mudou de formato: uma execução gravada antes não é reconhecida na
  retomada.
