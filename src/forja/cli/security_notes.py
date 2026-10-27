"""What the person is told about the security checks of gate 10 that cannot say as much as they
seem to: the checks that need the user's own rules or list, and the registries that do not say."""

NO_SAST = "SAST não executado: sem configuração de regras do Semgrep."
NO_LICENSES = (
    "Licenças não verificadas: a política não lista licenças proibidas "
    "(seção [licenses] forbidden)."
)
NO_LAYERS = "Camadas NÃO verificadas: sem regras em [architecture]."
UNMEASURED = (
    "Dependência nova: o uso (downloads) só é medido em npm e NuGet; em PyPI, Go e Maven não é "
    "medido, e no Go a idade também não (a data que o proxy dá é a do commit do autor)."
)


NO_E2E = "E2E não executado: sem comando (seção [adapters.<linguagem>.commands] e2e)."
FAKES = "E2E: fakes não validados por contrato; podem divergir do serviço real."
PROXY_LIMIT = (
    "E2E: rede desligada por armadilha de proxy; não impede cliente que ignora o proxy "
    "(soquete cru, Python http.client). Contenção forte é do ambiente."
)


def e2e_notices(*, declared: bool) -> tuple[str, ...]:
    """What the person is told of the E2E gate: that it did not run, or what its run cannot say."""
    return (FAKES, PROXY_LIMIT) if declared else (NO_E2E,)


NO_DIFFERENTIAL = "Teste diferencial não executado: sem casos (seção [[differential.cases]])."
DIFFERENTIAL_LIMIT = (
    "Teste diferencial: I/O não é medido; só tempo e memória, e só onde a plataforma mede."
)


def differential_notices(*, refactoring: bool, declared: bool) -> tuple[str, ...]:
    """What the person is told of gate 11, which only judges a refactoring: that it did not run,
    or what its run does not measure."""
    if not refactoring:
        return ()
    return (DIFFERENTIAL_LIMIT,) if declared else (NO_DIFFERENTIAL,)


def security_notices(*, rules: bool, licenses: bool, layers: bool) -> tuple[str, ...]:
    """The notices of a run: the SAST without rules, the licenses without a list, the layers
    without rules, and what the registries cannot measure."""
    return (
        *(() if rules else (NO_SAST,)),
        *(() if licenses else (NO_LICENSES,)),
        *(() if layers else (NO_LAYERS,)),
        UNMEASURED,
    )
