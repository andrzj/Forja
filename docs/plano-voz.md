# Plano: a voz como instrução, nunca como bloqueio (fila 10)

Origem: ordem do dono em 31/10/2026. "Nunca bloquear por voz. A Forja tem de buscar controlar como melhor conseguir, Agents.md, Claude.md, a estratégia que couber para cada ou todas as CLIs compatíveis, ou mesmo com SKILL.md (humanizer)."

## Decisão

1. **A voz nunca bloqueia.** O gate 12 (`voice`, `comments`) mede e reporta no resumo; nenhuma configuração o torna bloqueante. A Especificação (linhas 292 e 591) foi emendada: sai "a lista de marcadores é `bloqueante` por padrão".
2. **A Forja controla a voz na origem**, instruindo o agente antes de ele escrever, não reprovando o que ele escreveu. A referência é a skill `humanizer` (v2.9.1, MIT, lida por inteiro em 31/10/2026), que é a especificação do conteúdo; não se reescreve nem se "inspira" nela (regra 1 do `CLAUDE.md`).

## O que já existe (lido em 31/10/2026)

- O pacote vai por arquivo ou stdin, nunca como argumento. `agent_runner.py::build_package(ctx, redactor, facade=)` o monta; seções de texto fixo da Forja (como o pedido de hipótese do diário) entram sem passar pelo redator.
- A Forja **desliga de propósito** as instruções do projeto e as skills nas CLIs: Claude Code com `--setting-sources user`, `--disable-slash-commands`, `--strict-mcp-config`, `--no-session-persistence` (`executors\claude_code.py`); Codex sem `AGENTS.md` do repositório (`executors\codex.py`, docstring); Grok lê `AGENTS.md` e `.grok/rules` (`executors\grok.py`, docstring). Existem ainda `cursor.py` e `gemini.py`, e o adaptador genérico por modelo de comando (`[clis.<nome>]`, sem controle de permissão).
- O gate 12 hoje é `Mode.OBSERVATION` em `checks\specs.py` e a lista de marcadores é `checks\voice_markers.py` (`VERSION = 1`, `MAX_DASHES = 3`), configurável por `[voice] markers_extra/markers_off` (`core\policy\config.py`).
- Qualquer arquivo de instrução que a Forja ponha **dentro da worktree da tentativa** aparece no diff e cai no gate 1 (escopo). O caminho certo é um canal que não toque o diff.

## Passos (um por commit; registrar no Plano no mesmo commit)

**Passo 0 (feito em 31/10/2026): ler a documentação de cada CLI, citar a fonte.** Para Claude Code, Codex, Grok, Gemini e Cursor: quais canais de instrução a CLI oferece em modo headless (prompt de sistema adicional, `CLAUDE.md`/`AGENTS.md`/`GEMINI.md`/regras, skills), se algum cabe fora da worktree e se algum respeita o isolamento que a Forja já impõe. Nada de nome de opção de memória: só o que a documentação traz. Resultado: tabela CLI por canal em `docs\voz.md`, com fonte e limite. Saída do passo: a lista dos canais que valem a pena e a dos que não cabem.

**Passo 1: o texto da voz.** `orchestrator\voice_brief.py` (ou módulo equivalente), com texto versionado (`VERSION`) montado a partir do `humanizer` no modo embutido ("saída só o texto final, sem cerimônia"): os padrões da skill que valem para comentário de código, mensagem de commit e documentação, a regra de não inventar fato, a regra de não usar travessão e a de reaproveitar a voz que o repositório já tem. Idioma e padrões extras do repositório (`[voice]`) entram no texto. Texto fixo da Forja, não passa pelo redator.

**Passo 2: canal universal, o pacote.** `build_package` põe a seção de voz em toda chamada que escreve texto (implementador, autor de testes, especificador, arqueólogo, documentador). É o canal que vale para qualquer CLI, inclusive a genérica, e o único que não depende de recurso da CLI. O pacote efetivamente enviado já é registrado com hash, então a instrução fica auditável.

**Passo 3: canal próprio de cada CLI.** Resultado do passo 0 (`docs\voz.md`): só o **Claude Code** tem um canal documentado para `-p` que não toca o diff (`--append-system-prompt-file`, com o arquivo em `AGENT_DIR`, junto do `settings` que o adaptador já grava). O adaptador o declara como capacidade nova, com a operação planejável exigida pelo contrato `tests\core\adapters\conformance.py`. Codex, Grok e Gemini têm canal candidato mas a documentação não confirma o efeito em headless: ficam só com o pacote até uma chamada real (do dono) ou a documentação confirmar. Cursor e a CLI genérica: só o pacote. Skill (`SKILL.md`) não entra: o Claude Code a desliga com `--disable-slash-commands` e as outras não documentam carregamento em headless; o conteúdo do `humanizer` vai como texto.

**Passo 4: a voz nunca bloqueia.** A validação da política recusa `mode = "blocking"` para `voice` e `comments` (erro de configuração com mensagem que aponta esta decisão); `specs.py` mantém `OBSERVATION`; o resumo continua reportando o que o gate mediu. Teste de que a configuração é recusada.

**Passo 5: documentação e fecho.** `docs\voz.md` (o que a Forja instrui, por canal e por CLI; o que não garante), ADR (a voz é instrução e medida, não bloqueio; canais por CLI), emenda de `docs\limiares.md` (`max_dashes` e `comments` ficam como medidas), gate de mutação nos arquivos novos. O efeito real sobre a escrita dos agentes só um E2E real mostra: é do dono.

## Fora do plano

Reprovar tentativa por voz; calibrar `max_dashes`; mudar a lista de marcadores. Reescrever o texto do agente depois de escrito (a Forja não edita o que o agente produziu).
