# Voz: por onde a Forja instrui cada CLI

Resultado do passo 0 da fila 10 (`docs\plano-voz.md`), lido em 31/10/2026 nas páginas das próprias CLIs. A voz nunca bloqueia: a Forja a mede (gate 12) e tenta controlá-la na origem, instruindo o agente. Este documento diz por onde cada CLI aceita a instrução. Onde a documentação não diz, está escrito "não documentado"; nada foi suposto.

As leituras foram feitas por subagentes que citaram o URL de cada fato; conferi a coerência com o que os adaptadores já assumem, não reli as páginas uma a uma.

## O que a Forja faz

A voz é **instrução e medida, nunca bloqueio** (ADR 0035).

- **Instrui.** `orchestrator\voice_brief.py` guarda o texto (`VERSION = 1`), em inglês como o resto do pacote, a partir da skill `humanizer` v2.9.1 no modo embutido. Pede: não inventar fato, dizer o simples, seguir o idioma e os hábitos do repositório (hábito claro do repositório vale mais que a lista), deixar código, identificadores e citações como estão, escrever só o texto. Mais 20 padrões a evitar, entre eles cumprimento e elogio, falar de si, oferta de ajuda, anúncio de importância, vocabulário inflado, travessões (a instrução pede zero; a medida tolera 3), negrito e títulos em maiúsculas, emoji, voz passiva, texto que narra a mudança e palpite que preenche lacuna.
- **Acompanha a medida.** Regra ligada a um marcador do gate 12 (`greeting`, `self-reference`, `offer`, `announcement`, `inflated`, `emoji`) sai do texto quando o repositório desliga esse marcador em `[voice] markers_off`. Os padrões que o repositório acrescenta em `markers_extra` entram listados. Assim a instrução e a medida dizem a mesma coisa.
- **Entrega.** A seção `## Voice` entra no pacote de toda chamada que escreve texto (implementador, autor de testes, especificador, arqueólogo, documentador), em qualquer CLI, inclusive a genérica. O pacote enviado já é registrado com hash. No Claude Code o mesmo texto vai também como arquivo de prompt de sistema adicional (`--append-system-prompt-file`, com `instructions.md` em `.forja-agent`, fora do diff; o agente não pode editá-lo e mudá-lo rejeita o trabalho).
- **Mede.** O gate 12 (`voice` e `comments`) continua só em observação e o resumo reporta o que ele mediu. A política recusa `mode = "blocking"` para os dois: é erro de configuração.

## O que a Forja não garante

- **Efeito.** Instruir não faz o modelo obedecer. Só uma execução real, com agente real, mostra quanto a escrita muda; isso é do dono (E2E).
- **Canal próprio fora do Claude Code.** Codex, Grok e Gemini têm canal candidato (abaixo), mas a documentação não confirma o efeito em headless. A Forja não grava opção não confirmada, que pode derrubar a chamada. Esses três, o Cursor e a CLI genérica recebem só o pacote.
- **Idioma.** A política não tem chave de idioma. O texto manda seguir o idioma do texto ao redor.
- **Skills.** Nenhuma skill é carregada: o conteúdo do `humanizer` vai como texto.
- **Reescrita.** A Forja não edita o que o agente escreveu.

## Critério

Um canal serve se (a) leva texto de instrução ao modelo em modo headless, (b) não escreve na worktree da tentativa (o arquivo apareceria no diff e cairia no gate 1) e (c) não religa o que a Forja desliga de propósito (instruções e skills do projeto, MCP, hooks).

## Por CLI

| CLI | Canal que cabe | Fonte | Limite |
| --- | --- | --- | --- |
| Claude Code | `--append-system-prompt-file <arquivo>`: acrescenta ao prompt de sistema padrão. "All five work in both interactive and non-interactive modes." O arquivo pode ficar fora da worktree (a Forja já grava o `settings` do agente em `AGENT_DIR`). | `code.claude.com/docs/en/cli-reference#system-prompt-flags` e `/headless` | Documentado para `-p`. `--system-prompt` substitui o padrão e tira a orientação de ferramentas e segurança: não usar. |
| Codex | `developer_instructions` (string, "Additional developer instructions injected into the session") ou `model_instructions_file`, em `config.toml`; `-c chave=valor` sobrescreve configuração. `model_instructions_file` **substitui** as instruções embutidas: não usar. | `learn.chatgpt.com/docs/config-file/config-reference`, `/non-interactive-mode` | A documentação não diz que `-c` vale para essas chaves, nem a resolução de caminho em config de usuário. `CODEX_HOME` com `AGENTS.md` global é documentado, mas é a pasta do login do usuário: trocá-la tira o login. Não verificado em chamada real. |
| Grok Build | `--rules "<texto>"` acrescenta ao prompt de sistema; `--system-prompt-override` substitui (não usar). Regras globais em `~/.grok/` são lidas primeiro; `GROK_HOME` é a casa de config, e a Forja já usa uma própria. | `docs.x.ai/build/features/project-rules`, `/settings/reference` | `--rules` é só texto na linha de comando (a Forja não passa conteúdo por argumento) e a página de headless não o lista. Que `GROK_HOME` mude onde as regras globais são lidas: não documentado. Não verificado em chamada real. |
| Gemini CLI | `GEMINI.md` global em `~/.gemini`; `context.fileName` troca o nome; `--include-directories` (máx. 5) com `context.loadFromIncludeDirectories = true` carrega de fora do diretório de trabalho. `GEMINI_SYSTEM_MD` substitui o prompt de sistema inteiro: não usar. | `github.com/google-gemini/gemini-cli/blob/main/docs/cli/gemini-md.md`, `/system-prompt.md`, `google-gemini.github.io/gemini-cli/docs/get-started/configuration.html` | A página de headless não cita nenhum desses canais; vale em `-p`: não documentado. O adaptador já registra que o `GEMINI.md` do projeto não se desliga. Não verificado em chamada real. |
| Cursor CLI | Nenhum que caiba. Não há flag de instrução; regras do projeto (`.cursor/rules`, `AGENTS.md`, `CLAUDE.md` na raiz) ficariam na worktree; o caminho em disco das regras de usuário e a leitura de regras em `-p` não estão documentados. `CURSOR_CONFIG_DIR` só é citado para `cli-config.json`. | `cursor.com/docs/cli/using`, `/cli/reference/parameters`, `/cli/reference/configuration`, `/context/rules` | Só o pacote. |
| CLI genérica (`[clis.<nome>]`) | Só o pacote. | | |

## Skills

Nenhuma CLI tem, na documentação lida, um modo de carregar uma skill em headless sem religar as skills do usuário ou do projeto:

- **Claude Code:** `--disable-slash-commands` "disable all skills and commands for this session", e a Forja o passa. Uma skill só roda em `-p` se o prompt a invocar por `/nome` (e só a primeira). Tirar o `--disable-slash-commands` reabriria as skills do usuário. O conteúdo do `humanizer` entra, então, como texto no prompt de sistema, não como skill.
- **Gemini, Grok, Codex, Cursor:** o carregamento de skill em headless não está documentado, ou é um recurso do usuário ou do projeto.

## O que isto decide

1. **O pacote é o canal de toda CLI**, inclusive a genérica e o Cursor. É o único que não depende de recurso da CLI e já é registrado com hash.
2. **Claude Code ganha um segundo canal documentado**, o arquivo de prompt de sistema adicional (feito no passo 3: `InstructionChannel`, `ClaudeCodeAdapter.instruction_setup`).
3. **Codex, Grok e Gemini têm canal candidato, não verificado.** A Forja não grava opção que a documentação não confirma para modo headless: passar uma opção desconhecida pode derrubar a chamada. Esses canais só entram depois de uma chamada real que mostre que valem (E2E do dono) ou de a documentação passar a dizer.
4. **Nenhum canal substitui o prompt de sistema.** Substituir tira a orientação de ferramentas e segurança do padrão.
