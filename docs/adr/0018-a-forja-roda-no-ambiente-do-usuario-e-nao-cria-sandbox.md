# 0018. A Forja roda no ambiente do usuário e não cria sandbox

## Contexto

A especificação previa o WSL como nível padrão de isolamento (distribuição dedicada, rede por lista
de permissões) e um nível reduzido como alternativa. Em ambiente corporativo isso é caro e muitas
vezes impossível (WSL, contêineres e regras de rede dependem de política da empresa), e nenhum
software que a Forja usa depende de WSL ou de Linux.

## Decisão

- A Forja roda no terminal onde o usuário está. A infraestrutura e as permissões em volta (máquina,
  contêiner, máquina virtual, rede, credenciais) são responsabilidade do usuário ou da política da
  empresa, que se manifestam ao escolher onde rodar.
- Existe um único nível, `environment`. A Forja impõe o que funciona em qualquer sistema e não exige
  instalação: ambiente filtrado para a CLI, cópia sem `.git`, arquivos sensíveis ausentes da cópia,
  ferramentas de arquivo do agente confinadas à cópia, processos que não sobrevivem à Forja (Job
  Object no Windows) e conferência do git antes e depois de cada chamada (detecção).
- Leitura fora da cópia, rede e segredos do ambiente são declarados como responsabilidade do
  ambiente (`Status.ENVIRONMENT`). A confirmação e o resumo dizem isso com todas as letras.
- `forja agente testar` fica disponível: o agente pode rodar os testes do projeto na cópia dele, no
  ambiente do usuário, com ambiente reduzido da chamada. A confirmação declara isso e
  `agente_roda_testes = false` no `execucao.toml` desliga.
- Substitui, na especificação, a decisão 3 do plano (WSL como padrão) e os níveis WSL e reduzido.

## Consequências

Menos código e nenhuma dependência de plataforma. Quem precisa de contenção forte roda a Forja já
dentro dela (contêiner, VM, máquina dedicada); a Forja não promete o que não impõe.
