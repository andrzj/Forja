"""Only a CLI with a documented headless channel takes instructions outside the package."""

import pytest

from forja.core.adapters.executor import CommandTemplate, InstructionChannel, template_adapter
from forja.executors import KNOWN_CLIS, adapter_for


@pytest.mark.parametrize("name", sorted(KNOWN_CLIS))
def test_which_known_clis_have_a_channel_of_their_own(name: str) -> None:
    assert isinstance(adapter_for(name), InstructionChannel) is (name == "claude-code")


def test_the_generic_adapter_has_no_channel() -> None:
    template = CommandTemplate(("{executable}", "{package}"))

    assert not isinstance(template_adapter("mine", template), InstructionChannel)
