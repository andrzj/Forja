"""What the person is told about the security checks of gate 10 that cannot say as much as they
seem to: the checks that need the user's own rules or list, and the registries that do not say."""

NO_SAST = "SAST não executado: sem configuração de regras do Semgrep."
NO_LICENSES = (
    "Licenças não verificadas: a política não lista licenças proibidas "
    "(seção [licenses] forbidden)."
)
UNMEASURED = (
    "Dependência nova: o uso (downloads) só é medido em npm e NuGet; em PyPI, Go e Maven não é "
    "medido, e no Go a idade também não (a data que o proxy dá é a do commit do autor)."
)


def security_notices(*, rules: bool, licenses: bool) -> tuple[str, ...]:
    """The notices of a run: the SAST without rules, the licenses without a list, and what the
    registries cannot measure."""
    return (
        *(() if rules else (NO_SAST,)),
        *(() if licenses else (NO_LICENSES,)),
        UNMEASURED,
    )
