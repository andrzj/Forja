"""What the run tells the person about the E2E gate, and where its commands come from."""

from forja.cli.security_notes import FAKES, NO_E2E, PROXY_LIMIT, e2e_notices
from forja.cli.session import e2e_commands
from forja.core.policy.config import EffectivePolicy


def test_without_a_command_the_person_is_told_the_e2e_did_not_run() -> None:
    assert e2e_notices(declared=False) == (NO_E2E,)


def test_with_a_command_the_person_is_told_what_the_run_cannot_say() -> None:
    assert e2e_notices(declared=True) == (FAKES, PROXY_LIMIT)


def test_only_the_languages_that_declare_an_e2e_command_have_one() -> None:
    policy = EffectivePolicy(
        checks={},
        adapter_commands={
            "python": {"e2e": ("pytest", "e2e"), "lint": ("ruff",)},
            "go": {"lint": ("golangci-lint",)},
        },
    )

    assert e2e_commands(policy) == {"python": ("pytest", "e2e")}
