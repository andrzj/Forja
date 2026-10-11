# 0004. Adaptadores descrevem; o núcleo executa

- Status: Aceito
- Data: 10/10/2026

## Contexto

Adaptadores de linguagem e de executor cercam ferramentas que mudam com frequência. Se cada adaptador criasse seus próprios processos, o Job Object, o isolamento, o mutex de git e o registro das execuções teriam de ser repetidos e verificados em cada um.

## Decisão

O adaptador só descreve o que deve ser executado (um plano de comando) e interpreta a saída. Quem executa é o núcleo, pelo executor de processos. Uma operação que o adaptador não suporta devolve `NotSupported`, nunca uma exceção. Capacidades declaradas e operações implementadas devem ser consistentes, e uma suíte de conformidade reutilizável (`tests/core/adapters/conformance.py`) é passada por todo adaptador. O `config_hash` da chave de cache é calculado pelo núcleo: argumentos, nomes das variáveis de ambiente e arquivos de configuração declarados.

## Consequências

- Um adaptador novo não consegue contornar o isolamento nem o registro.
- Testar um adaptador não exige processos reais, só o plano e a interpretação da saída.
- A descoberta de executores segue uma ordem fixa: arquivo de execução ou flag, variável `FORJA_EXECUTOR_<NOME>`, configuração do usuário, descoberta.

Ver a especificação, seções "Contrato do adaptador" e "Executores de CLI".
