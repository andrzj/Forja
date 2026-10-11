# Forja — plano de execução

## Estratégia

A Forja será construída em incrementos, cada um entregando algo que funciona de ponta a ponta, e a expansão só acontece depois que a tese for medida contra uma linha de base. O risco principal do projeto não é faltar algo no desenho, é tentar construí-lo inteiro de uma vez (efeito segundo sistema, Brooks; lei de Gall: um sistema complexo que funciona evoluiu de um sistema simples que funcionava).

### O que entra na estrutura desde o primeiro dia

Mudar estes pontos depois exigiria refazer o núcleo, por isso eles nascem completos, mesmo que pouco usados no início:

- os cinco contratos centrais: estados e transições, protocolo de subprocesso e idempotência, autorização e isolamento, eventos, artefatos e evidências, e gate;
- esquema único de evidências;
- contratos de artefatos entre papéis;
- interfaces de adaptador de linguagem e de executor;
- contrato de saída do LLM (afirmação, ação, premissa);
- redação do pacote antes do envio.

### Decisões técnicas da implementação

- Python 3.12 ou superior, distribuído como ferramenta instalável por `uv tool` ou `pipx`.
- Esquemas de artefatos e evidências com validação tipada (pydantic).
- Executor de processos assíncrono (asyncio) no núcleo, dono do ciclo de vida dos subprocessos; a interface só consome eventos.
- Interface com Textual sobre Rich; renderizador de texto simples para CI.
- TOML apenas para valores (limiares, modo de cada gate, comandos, limites); predicados e lógica dos gates em código.
- A própria Forja usa o adaptador de Python e passa pelos próprios gates a partir do incremento 1.

## Incrementos

São oito incrementos, de 0 a 7. O incremento 2 é um ponto de decisão: os seguintes só começam se a medição sustentar a tese.

### 0. Fundação

**Escopo:** estrutura do projeto; os cinco contratos centrais como código e testes (máquina de estados, executor de processos com tabela de idempotência, política de autorização, esquemas de eventos, artefatos e evidências com proveniência, contrato de gate com quatro resultados, combinação validada de modo e política, modo observação e chave de cache completa); registros em camadas (execução de ferramenta, evidência, decisão de gate); capacidades declaradas de adaptador; versão de esquema em eventos e artefatos, com conversão na leitura; armazenamento de artefatos por hash; JSONL com hash encadeado, intenção e efetivação; escrita atômica; esquemas de evidências e artefatos; interfaces de adaptador de linguagem e de executor; contrato de saída do LLM; redação do pacote; lock por repositório; testes de injeção de falhas da camada de persistência.

**Pronto quando:** a máquina de estados rejeita transições não permitidas; cada operação da tabela de idempotência tem teste de reconciliação; a retomada chega ao mesmo estado após interrupção em cada fronteira de passo, comprovado por teste; a redação remove segredos e dados pessoais de um conjunto de fixtures conhecidas.

### 1. Esqueleto ponta a ponta

**Escopo:** adaptador de Python; uma CLI; só o papel de implementador; objetivo de refatoração; normalização (`style:`); gates de escopo, segredos, lint com catraca, build, testes e complexidade; gestor de git com branch por tarefa, worktree por tentativa, commit por etapa, integração da tarefa inteira, trailers e verificação de HEAD, índice e refs antes e depois de cada chamada; agente em cópia de trabalho sem .git, com transferência por manifesto para o worktree; build, testes e demais ferramentas executados dentro do sandbox, com caches separados por repositório; isolamento do contrato 3 (distribuição WSL dedicada, com nível reduzido declarado quando não houver WSL) e Job Object; fachada `forja agente testar`; preparação guiada com descoberta e prova de vida; interface com progresso, atividade do agente e observação do worktree; retomada completa.

**Pronto quando:** em três repositórios Python de exemplo, uma execução vai do comando à entrega sem intervenção; interrupções forçadas em qualquer passo retomam e chegam ao mesmo estado final; uma CLI que tenta usar git falha; sob WSL, ela não consegue ler arquivos fora da cópia de trabalho nem acessar rede fora da lista de permissões; sem WSL, a preparação avisa e o resumo declara o nível reduzido; a própria Forja passa nos seus gates.

### 2. Medição contra linha de base (ponto de decisão)

**Escopo:** experimento com o mesmo conjunto de tarefas executado por uma CLI apenas com prompt e pela Forja. Métricas: taxa de entregas aceitas por um revisor, regressões introduzidas, tempo, tentativas e consumo quando a CLI informar.

**Pronto quando:** relatório com os números e decisão registrada (seguir, ajustar ou parar), com o motivo.

### 3. Prova forte

**Escopo:** papel de autor de testes; gate vermelho/verde; congelamento de testes; mutação e CRAP; métricas opostas (*pass-through*, profundidade de módulo); segunda CLI com diversidade de autor; adaptador de TypeScript; cache de medições pela chave completa do contrato 5.

**Pronto quando:** num conjunto de tarefas com defeitos plantados, testes que não verificam nada são rejeitados pelo gate; uma refatoração que cria métodos rasos é rejeitada mesmo com CRAP melhor.

### 4. Documentação

**Escopo:** papel de documentador como etapa final obrigatória de toda tarefa que altera código; registro de mudança por tarefa; avaliação e correção do README; ADR por regra; deriva; linter de voz para comentários, commits e documentação; resumo da execução e estrutura do resumo de entrega.

**Pronto quando:** toda tarefa aprovada carrega seu registro no mesmo commit; um README com comando de build divergente é detectado e corrigido apenas na seção afetada.

### 5. Amplitude

**Escopo:** adaptadores de Java, Go e C#; JavaScript completo; modelo arquitetural global (grafo, ciclos, métricas de pacote, camadas); teste diferencial com medição de tempo e memória; E2E com fakes e rede desligada; segurança completa (Semgrep, OSV-Scanner, licenças, verificação de dependência nova).

**Pronto quando:** a suíte de avaliação, com repositórios de exemplo nas seis linguagens, executa ponta a ponta; uma refatoração que cria ciclo de dependência é rejeitada; um E2E que acessa rede falha.

### 6. Ideia, especificação e engenharia reversa

**Escopo:** papéis de arqueólogo e especificador; rastreabilidade ideia → critério → teste; andaime determinístico por template; modo a partir de diretório vazio; premissas e fatos registrados completos; coleta do resultado da revisão a partir do git.

**Pronto quando:** a partir de uma especificação de exemplo, a Forja entrega um projeto com testes que cobrem todos os critérios; a documentação de engenharia reversa separa fatos provados, fatos confirmados e premissas.

### 7. Endurecimento

**Escopo:** paralelismo de tarefas com escopos disjuntos; mutação incremental; prevenção de suspensão; modo CI com `--config`; adaptador genérico de CLI; calibração de limiares e promoção de gates do modo observação para bloqueante com dados da revisão; documentação de uso da Forja.

**Pronto quando:** a suíte de avaliação roda em CI a cada mudança de política ou de versão de CLI, e os limiares estão calibrados com dados reais de revisão.

## Riscos e mitigação

| Risco | Impacto | Mitigação |
| --- | --- | --- |
| Escopo excessivo na primeira versão | Projeto longo sem entrega útil | Incrementos com critério de pronto; decisão explícita no incremento 2 |
| A tese não se confirma na medição | Investimento sem retorno | Incremento 2 antes de qualquer expansão; critérios de sucesso definidos antes |
| CLIs mudam flags, formatos de saída e comportamento com frequência | Execuções quebram após atualizações | Adaptadores isolados; prova de vida por versão; suíte de avaliação a cada atualização |
| Gates rígidos demais bloqueiam quase tudo; frouxos demais aprovam código ruim | Ferramenta inútil ou perigosa | Catraca; limiares por linguagem; modo observação para gates sem calibração; calibração com dados da revisão |
| Mutação lenta em repositórios grandes | Execuções de muitas horas | Mutação incremental e restrita ao código tocado; cache pela chave completa |
| Ferramentas de mutação imaturas em Go e Python | Falsos resultados | Limiares próprios; mutação como métrica informativa onde for frágil |
| Fakes divergem dos serviços reais | E2E verdes com comportamento real quebrado | Fakes gerados ou validados por contrato; divergência possível declarada como premissa |
| Restrições corporativas (containers, rede, instalação de ferramentas, WSL) | Isolamento ou ferramentas indisponíveis | WSL presumido como padrão; sem ele, aviso na preparação, nível reduzido com garantias declaradas e registro no resumo |
| Terminal do Git Bash (mintty) incompatível com interface rica | Experiência degradada | Detecção e aviso; recomendação de Windows Terminal; renderizador de texto simples |
| Envio de código sensível ao provedor do modelo | Exposição de dados | Redação obrigatória do pacote; exclusões por configuração; auditoria do pacote enviado |
| Agente altera o git (commit, reset, refs compartilhadas pelo worktree) | Estado da execução inconsistente; retomada incorreta | Agente em cópia sem .git; verificação de HEAD, índice e refs antes e depois de cada chamada, desde o incremento 1 |
| Ferramenta de medição falha ou não suporta o código | Aprovação silenciosa ou culpa indevida do agente | Resultado inconclusivo com política por gate (contrato 5) |
| Evidência reaproveitada de outro contexto de medição | Gate decide com dado desatualizado | Chave de cache com commit, ferramenta, configuração, toolchain, plataforma e escopo |
| CLI lê arquivos que não estavam no pacote | Dados sensíveis expostos ao provedor do modelo | Cópia de trabalho sem arquivos sensíveis; leitura restrita à cópia no nível WSL; limite declarado no nível reduzido |
| Falhas de infraestrutura repetem chamadas à CLI | Custo sem limite | Consumo por chamada; limite de falhas consecutivas por etapa; pausa da execução |
| Evolução do formato de eventos e artefatos | Execuções antigas não retomam ou retomam errado | Versão de esquema; conversão na leitura; recusa explícita de versão desconhecida |
| Política corporativa restringe a distribuição WSL ou o controle de rede dentro dela | Nível WSL indisponível | Verificar no incremento 1; nível reduzido como alternativa declarada |
| Alterações do agente não representáveis no worktree (links simbólicos, nomes que diferem só em maiúsculas, caminhos longos) | Worktree inconsistente com a cópia | Transferência por manifesto; tentativa rejeitada com motivo explícito |

## Questões em aberto para a revisão

Pontos que ainda não têm decisão e que a revisão deve ajudar a fechar:

1. **Limiares iniciais por linguagem:** CRAP, complexidade, cobertura e score de mutação para começar, antes de haver dados de calibração.
2. **Formato das políticas:** decidido: predicados em código e TOML apenas para valores. Falta definir o esquema desses valores por linguagem.
3. **Isolamento na estação Windows:** decidido: WSL como padrão e nível reduzido com Git Bash no Windows Terminal quando não houver WSL. Falta confirmar se a política corporativa permite importar uma distribuição dedicada e controlar a rede de saída dentro dela.
4. **Consumo de tokens:** nem todas as CLIs informam consumo de forma estruturada; definir se o custo será medido por tokens, tempo ou ambos. Fontes possíveis: a própria CLI ou os relatórios do gateway corporativo; a Forja não intermedia as chamadas ao modelo.
5. ~~**Plataforma de PR**~~ — decidido: sem PR e sem integração com plataforma. A entrega é a branch da execução mais o resumo; a coleta da revisão usa só o que o git mostra.
6. **Valores padrão:** número de tentativas por tarefa, limite de arquivos e linhas por tarefa, limite de tarefas por execução e orçamento de tempo.
7. **Tamanho máximo do pacote** de evidências e critério de corte quando os hotspots excederem esse limite.
8. **Conjunto de repositórios da suíte de avaliação:** quais projetos de exemplo, com quais defeitos plantados, em cada linguagem.
9. **Nome e distribuição interna** da ferramenta.
10. **Padrão do lock por repositório:** recusa imediata ou espera com limite quando houver outra sessão da Forja (recomendação: recusa no modo interativo, espera em CI). Fecha-se no incremento 1.
