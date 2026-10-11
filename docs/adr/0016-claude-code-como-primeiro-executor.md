# 0016. Claude Code como primeiro executor e o runner de CLI

- Status: Aceito
- Data: 11/10/2026

## Contexto

O incremento 1 precisava de um agente de verdade. O contrato de adaptador de executor, a descoberta e a prova de vida já existiam desde o incremento 0; faltavam o adaptador do Claude Code e um `AgentRunner` que o usasse. Duas descobertas da gravação de uma chamada real mudaram o desenho: os hooks do perfil do usuário rodam dentro da chamada (e injetam texto no que o agente lê), e uma CLI chamada com o ambiente de outra sessão falha a autenticação.

## Decisão

- **A CLI é do usuário.** Instalação, login (assinatura ou chave), modelo e gateway são feitos antes. A Forja nunca configura nem autentica nada: verifica na prova de vida (`forja doctor`, no incremento 1f) e a documentação de setup lista os pré-requisitos.
- **Invocação** (`executors/claude_code.py`): `claude -p --output-format stream-json --verbose --permission-mode dontAsk`, pacote por **stdin**, `--setting-sources user` (as configurações do repositório não são lidas: seriam instruções ao agente), `--settings .forja-agent/claude-settings.json` com `disableAllHooks`, `--strict-mcp-config`, `--disable-slash-commands`, `--no-session-persistence` e `--tools`/`--allowedTools` do papel. Sem `--bare`, que só aceita chave de API e recusaria o login do usuário.
- **Ambiente por lista de permissão.** Passam as variáveis de configuração da própria CLI (chave, URL do gateway, modelo, nuvem, proxy, certificados, `APPDATA`); as `CLAUDE_CODE_*` de um aplicativo hospedeiro ficam de fora, pois descrevem outra sessão.
- **Permissões do implementador no 1d:** leitura, edição e escrita; Bash negado. A fachada `forja agente ...` e os comandos permitidos chegam no 1f.
- **Saída do agente:** o contrato que já existia (`LlmOutput`: ações com arquivos e motivo, premissas, afirmações com citação) em `.forja-agent/saida.json`. Os arquivos declarados precisam ser os que mudaram (manifesto antes e depois), com o mesmo tipo de mudança, senão o trabalho é rejeitado e a divergência volta ao agente. O motivo do commit é a junção dos motivos das ações.
- **Cópia de trabalho** sem `.git`, com `.forja-agent/` (pacote, configurações, saída) reservado dentro dela e fora dos manifestos. O pacote passa pelo redator: segredos mascarados, arquivos sensíveis retidos e ditos como retidos.
- **Tokens:** o evento `result` do fluxo traz o uso. Conta-se o enviado (entrada mais criação de cache) e o escrito; a leitura de cache não conta. O evento `agent_activity` do tipo `usage` alimenta o medidor.
- **Travamento** não é orçamento: 5 minutos sem nenhuma linha de saída encerram a árvore de processos e valem como falha transitória.
- **Orçamento é de tokens** (`Budget.tokens`, padrão 2.000.000). O `Meter` lê o log. `enforce` só vale sem pessoa (CI): com terminal a Forja mostra o quanto passou e quem decide é o usuário. O tempo é só exibido. A espera de rede não tem limite de tempo (`max_network_probes` limita quando não há quem interrompa).
- **Planejador sem modelo** (`ComplexityPlanner`): as funções mais complexas acima do limite do lizard, uma tarefa por função, dentro do orçamento de tarefas, arquivos e linhas.

## Revisão de segurança do commit

- **`.git` e arquivos sensíveis (corrigido).** O que volta da cópia é recusado se passar pelo diretório do git (qualquer grafia que o sistema aceite: caixa, ponto ou espaço no fim, nome curto `GIT~1`, aninhado) ou se criar ou alterar um arquivo sensível, mesmo declarado. Um `.git` plantado poderia redirecionar o git do worktree ou instalar hooks. Os arquivos sensíveis (`.env*`, `*.pem`, `secrets/**` etc.) também **não entram na cópia**: o agente não os lê, e eles voltam intactos (a limpeza do worktree os preserva e o resumo de reconciliação os conta).
- **Ferramentas de arquivo (parcial).** O arquivo de configurações gerado nega `Read`, `Edit` e `Write` em `../**` e `~/**`. A CLI aceita o arquivo, mas o efeito só se confirma com o teste `live`. Um caminho absoluto fora desses dois não é coberto por regra nenhuma: o que mantém a CLI dentro da cópia é o nível de isolamento (1e). A CLI tem `--restricted`, que confina as ferramentas de arquivo ao diretório de trabalho, mas também ignora as configurações do usuário (gateway, modelo); decidir entre honrar essas configurações e confinar fica registrado como pergunta aberta para o 1e.

- **Segunda revisão (corrigida).** (1) Os nomes são lidos como o Windows os lê (`.env.` e `.env ` são `.env`) antes de comparar com os padrões sensíveis, e um nome novo com marca de nome curto (`ENV~1`) é recusado; depois da volta, confere-se que os arquivos que deviam ficar intactos continuam iguais. (2) Links simbólicos ficam fora da cópia e voltam intactos, como os sensíveis: o agente não recebe o link nem o que ele aponta. (3) As configurações geradas negam `Edit` e `Write` nelas mesmas e no pacote, e a volta recusa o trabalho se o agente as alterou.

- **Terceira revisão (corrigida).** Um caminho novo abaixo de um link que já existe no worktree seria escrito através dele. Agora nada pode ser escrito num caminho escondido nem abaixo dele (comparação em forma normal do Windows e sem distinguir caixa), e a cópia de volta recusa qualquer destino que passe por um link.

## Consequências

- O mesmo `ExecutorAgentRunner` serve a qualquer CLI com um `ExecutorAdapter`; um adaptador novo só descreve a invocação e lê o fluxo.
- Os formatos das chamadas de ferramenta (`tool_use`) seguem o `stream-json` documentado, mas só a falha de autenticação foi gravada de uma CLI real: a chamada feliz depende do login do usuário. O teste `tests/executors/test_live.py` (`FORJA_LIVE=1`) confere tudo contra a CLI real.
- O uso de tokens só chega ao fim de cada chamada, então o percentual do orçamento atualiza nesse ritmo, e uma chamada interrompida pelo usuário não conta o que gastou até ali.
- Ctrl+K, a linha de status e o `forja doctor` ainda não existem (1f).
