"""The ``[voice]`` section: what a repository adds to the voice list and what it turns off."""

from pathlib import Path

import pytest

from forja.checks.specs import default_registry
from forja.core.policy.config import (
    EffectivePolicy,
    PolicyConfigError,
    build_policy,
    parse_layer,
)
from forja.core.policy.snapshot import freeze_policy, load_frozen_policy

OFF = '[voice]\nmarkers_off = ["emoji", "offer"]\n'
EXTRA = '[voice]\nmarkers_extra = ["\\\\bsynergy\\\\b"]\n'


def policy(*toml: str) -> EffectivePolicy:
    layers = [parse_layer(f"layer {i}", text) for i, text in enumerate(toml)]
    return build_policy(default_registry(), layers)


def test_the_voice_lists_are_the_repositorys_and_add_up_across_layers() -> None:
    found = policy(OFF, '[voice]\nmarkers_off = ["greeting", "emoji"]\n' + EXTRA.split("\n", 1)[1])

    assert found.voice_off == ("emoji", "offer", "greeting")
    assert found.voice_extra == ("\\bsynergy\\b",)
    assert policy().voice_off == () and policy().voice_extra == ()


@pytest.mark.parametrize(
    "text",
    [
        '[voice]\nmarkers_off = "emoji"\n',
        "[voice]\nmarkers_off = [1]\n",
        '[voice]\nmarkers_off = ["Emoji"]\n',
        '[voice]\nmarkers_off = ["a b"]\n',
        '[voice]\nmarkers_extra = ["("]\n',
        '[voice]\nmarkers_extra = ["x*"]\n',
        "[voice]\nmarkers_on = []\n",
        "voice = 1\n",
    ],
)
def test_a_voice_section_that_is_not_one_is_refused(text: str) -> None:
    with pytest.raises(PolicyConfigError):
        policy(text)


def test_the_voice_lists_are_part_of_the_digest_only_when_they_are_set() -> None:
    assert "voice" not in policy().to_dict()
    assert policy(OFF).to_dict()["voice"] == {
        "markers_extra": [],
        "markers_off": ["emoji", "offer"],
    }
    assert policy().digest() != policy(OFF).digest()


def test_the_frozen_policy_keeps_the_voice_lists(tmp_path: Path) -> None:
    original = policy(OFF, EXTRA)
    freeze_policy(original, tmp_path, "1.2.3")

    loaded = load_frozen_policy(default_registry(), tmp_path)

    assert loaded.policy.voice_off == original.voice_off
    assert loaded.policy.voice_extra == original.voice_extra
