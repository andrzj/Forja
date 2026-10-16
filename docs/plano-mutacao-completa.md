# Plano: mutação completa (linha sem teste volta ao autor de testes; seis linguagens)

Origem: decisões do dono em 16/10. (2) Toda linha nova precisa de teste; sem teste não há o que mutar, e o trabalho volta ao agente dos testes e depois à mutação. (4) A mutação precisa funcionar em Python, Go, Java, C# e JS/TS; os adaptadores que faltarem serão construídos.

## Feito (`333c8e5`)

- `MutationCheck` rejeita a tentativa quando uma linha adicionada não é executada por nenhum teste (um achado por linha, `untested_lines`), em vez de aprová-la.
- Limiar padrão 0,80; 0,70 para Python e Go; configurável por linguagem no TOML.
- Supressão obsoleta `PlainRenderer.update` removida.

## Parte A — o retorno ao autor de testes (orquestrador)

Hoje a rejeição do `MutationCheck` volta ao implementador (`TaskCycle._last_rejection`). Pedido: a rejeição por linha sem teste vai ao papel `TEST_AUTHOR`, e depois a mutação roda de novo.

Fatos vistos: `TaskCycle.run` percorre `roles(task_id)` uma vez (autor, depois implementador); testes são congelados no commit do estágio do autor (`FreezeCheck`); `ScopeCheck` impede o implementador de mexer em testes; o id do estágio do autor é `{task}-t`.

### Feito (Parte A) e desvios do desenho

Implementado em `core/gates/models.py` (`FindingKind`), `checks/mutation.py`, `orchestrator/task_cycle.py`, `orchestrator/measurer.py`, `checks/changes.py`; testes em `tests/orchestrator/test_untested_return.py` e `test_untested_resume.py`.

1. O achado "linha sem teste" é o campo `Finding.kind = FindingKind.UNTESTED_LINE` (nunca o texto). O ciclo só desvia a tentativa quando **todos** os achados da rejeição têm esse tipo e o estágio é o do implementador.
2. A tentativa rejeitada é **mantida num commit** (`commit_stage`, operação do diário da própria tentativa) na ramificação da tarefa, com o payload `untested` na transição `REJECTED`. O desenho original dizia "com o código do implementador como base" mas a tentativa rejeitada não era guardada; sem o commit o autor não veria o código. Consequência: o estágio do implementador não pede nova chamada ao agente.
3. O estágio extra é `{task}-t2` (`-t3`… se houvesse outra volta), tentativas `{task}-t2a<k>`, papel `TEST_AUTHOR`, `TaskInfo.reviews = "{task}-s"`. A razão da primeira tentativa é a rejeição do implementador com prefixo explicando o pedido. Vale também para refactor (sem estágio `-t`); `test_root` vazio cai em `planner.TEST_ROOT`.
4. **Desvio:** a mutação roda de novo **dentro do próprio estágio extra**, não numa nova chamada ao implementador. O `PipelineMeasurer.judge` do estágio extra: escopo, segredos, formato, lint, build e testes sobre o que o autor mudou (testes passam, não são vermelhos; sem `RedGreenCheck`); mutação, complexidade, CRAP, pass-through e profundidade sobre o código do implementador lido contra o commit anterior ao dele (`read_changes(git, base)`; base achada pelo trailer `Stage-Id`). Sobrevivente de mutação ou outro achado nessa rodada volta ao próprio autor (mais tentativas do estágio extra).
5. Depois que o estágio extra faz commit, o estágio do implementador também vai a `COMMITTED`. O congelamento dos testes novos fica no `frozen_digest` do estágio extra.
6. Teto: o estágio extra tem o orçamento `attempts_per_task` de qualquer estágio; esgotado, o estágio do implementador vai a `EXHAUSTED` (`tests_for_new_lines_exhausted`, com `detail` e `lines`) e a tarefa a `BLOCKED` com esse payload. Como o estágio do implementador termina na primeira volta, há no máximo uma volta por tentativa aceita; não há contador separado de voltas.
7. Retomada: ids determinísticos; teste de corte em cada linha do log (limpo e com linha rasgada) em `test_untested_resume.py`.

Não coberto por teste automático: o ramo `reviews` do `PipelineMeasurer.judge` com git e ferramentas reais (só `read_changes`/`read_before` com base, em `tests/checks/test_changes.py`).

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
