# Plano: mutação completa (linha sem teste volta ao autor de testes; seis linguagens)

Origem: decisões do dono em 16/10. (2) Toda linha nova precisa de teste; sem teste não há o que mutar, e o trabalho volta ao agente dos testes e depois à mutação. (4) A mutação precisa funcionar em Python, Go, Java, C# e JS/TS; os adaptadores que faltarem serão construídos.

## Feito (`333c8e5`)

- `MutationCheck` rejeita a tentativa quando uma linha adicionada não é executada por nenhum teste (um achado por linha, `untested_lines`), em vez de aprová-la.
- Limiar padrão 0,80; 0,70 para Python e Go; configurável por linguagem no TOML.
- Supressão obsoleta `PlainRenderer.update` removida.

## Parte A — o retorno ao autor de testes (orquestrador)

Hoje a rejeição do `MutationCheck` volta ao implementador (`TaskCycle._last_rejection`). Pedido: a rejeição por linha sem teste vai ao papel `TEST_AUTHOR`, e depois a mutação roda de novo.

Fatos vistos: `TaskCycle.run` percorre `roles(task_id)` uma vez (autor, depois implementador); testes são congelados no commit do estágio do autor (`FreezeCheck`); `ScopeCheck` impede o implementador de mexer em testes; o id do estágio do autor é `{task}-t`.

Desenho a confirmar na leitura de `phases.py`, `state.py` e `resume`:
1. Um achado do tipo "linha sem teste" é distinguido dos demais (campo no `Finding`, não texto).
2. Quando o estágio do implementador termina rejeitado só por esse tipo de achado, o ciclo abre um estágio extra do autor (`{task}-t2`, `-t3`…), com a lista de linhas como intenção e com o código do implementador como base; o congelamento passa a incluir os testes novos.
3. Depois do estágio extra, o implementador reavalia (mutação de novo). Teto: `attempts_per_task` do orçamento vale também para as voltas; esgotado, a tarefa fica bloqueada com o motivo.
4. Retomada: o estágio extra tem ids determinísticos e transições no log como os demais; teste de corte em cada fronteira (como `test_fix_resume.py`).

## Parte B — adaptadores das linguagens que faltam

Cada adaptador implementa `LanguageAdapter` (`core/adapters/language.py`): detecção, classificação de arquivos, formatação, lint, build, testes e cobertura, mais o leitor do relatório de cobertura (`ReportingAdapter`). Ferramentas por linguagem na Especificação (tabela das linhas 386-392).

Ambiente desta máquina (visto): Go, .NET e Node instalados; Java só o 8 antigo e sem Maven nem Gradle. Java exige instalar JDK atual e Maven ou Gradle antes dos testes reais (decisão do dono: quem instala as ferramentas é o usuário; o `doctor` só checa).

Ordem proposta, uma sessão por linguagem, cada uma terminando com a conformância dos adaptadores e um teste de mutação real de ponta a ponta:
1. Go (`gofmt`, `golangci-lint`, `go test -coverprofile`).
2. JavaScript/TypeScript (Prettier, ESLint, `tsc`, jest ou vitest, c8/istanbul).
3. C# (`dotnet format`, `dotnet test`, coverlet).
4. Java (Spotless, Checkstyle/PMD, Maven ou Gradle, JaCoCo).

O leitor de cobertura de cada formato já existe em `core/reports` (`go_coverprofile`, `istanbul_json`, `cobertura_xml`, `jacoco_xml`), com fixtures escritas à mão: a primeira tarefa de cada adaptador é gravar uma fixture real.

## Pronto quando

Uma tentativa com linha nova sem teste volta ao autor de testes e só passa pela mutação depois que o teste existe (teste de orquestrador com agente roteirizado e teste de retomada); para cada uma das seis linguagens, um projeto mínimo tem a mutação rodando de verdade e rejeitando teste vazio.
