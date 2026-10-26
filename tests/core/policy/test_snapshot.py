import json
from pathlib import Path

import pytest

from forja.core.gates import InconclusivePolicy, Mode
from forja.core.policy import (
    SNAPSHOT_NAME,
    CheckSpec,
    PolicyConfigError,
    build_policy,
    freeze_policy,
    load_frozen_policy,
    parse_layer,
)
from tests.core.policy.test_config import make_registry

PROMOTED = """
[checks.complexity]
mode = "blocking"
promotion = { date = 2026-10-10, reason = "calibrated" }
[checks.complexity.thresholds.python]
max_complexity = 10
[checks.build.commands]
build = ["uv", "build"]
"""


def effective(toml: str = PROMOTED):  # type: ignore[no-untyped-def]
    return build_policy(make_registry(), [parse_layer("repo", toml)])


def test_freezing_writes_one_canonical_file_and_returns_the_version(tmp_path: Path) -> None:
    policy = effective()

    version = freeze_policy(policy, tmp_path, "1.2.3")

    assert version == policy.version("1.2.3")
    assert [p.name for p in tmp_path.iterdir()] == [SNAPSHOT_NAME]
    document = json.loads((tmp_path / SNAPSHOT_NAME).read_bytes())
    assert document["policy_version"] == version


def test_the_frozen_policy_reads_back_identical(tmp_path: Path) -> None:
    policy = effective()
    version = freeze_policy(policy, tmp_path, "1.2.3")

    frozen = load_frozen_policy(make_registry(), tmp_path)

    assert frozen.version == version
    assert frozen.policy == policy
    complexity = frozen.policy.checks["complexity"]
    assert complexity.settings.mode is Mode.BLOCKING
    assert complexity.promotion is not None and complexity.promotion.date == "2026-10-10"


def test_later_edits_to_the_toml_never_reach_a_run_that_froze_its_policy(tmp_path: Path) -> None:
    freeze_policy(effective(), tmp_path, "1.2.3")
    edited = effective("[checks.complexity.thresholds.python]\nmax_complexity = 99\n")

    frozen = load_frozen_policy(make_registry(), tmp_path)

    assert frozen.policy.checks["complexity"].thresholds == {"python": {"max_complexity": 10}}
    assert edited.version("1.2.3") != frozen.version


def test_a_frozen_file_edited_by_hand_is_refused(tmp_path: Path) -> None:
    freeze_policy(effective(), tmp_path, "1.2.3")
    path = tmp_path / SNAPSHOT_NAME
    path.write_bytes(path.read_bytes().replace(b'"max_complexity":10', b'"max_complexity":11'))

    with pytest.raises(PolicyConfigError, match="does not match its version"):
        load_frozen_policy(make_registry(), tmp_path)


def test_a_changed_version_string_is_refused(tmp_path: Path) -> None:
    freeze_policy(effective(), tmp_path, "1.2.3")
    path = tmp_path / SNAPSHOT_NAME
    document = json.loads(path.read_bytes())
    document["policy_version"] = "1.2.3+000000000000"
    path.write_text(json.dumps(document))

    with pytest.raises(PolicyConfigError, match="does not match its version"):
        load_frozen_policy(make_registry(), tmp_path)


def test_a_check_added_to_the_code_after_the_run_started_is_noticed(tmp_path: Path) -> None:
    freeze_policy(effective(), tmp_path, "1.2.3")
    newer = make_registry()
    newer.register(CheckSpec("fresh", 10, Mode.BLOCKING, InconclusivePolicy.BLOCK))

    with pytest.raises(PolicyConfigError, match="changed since the run started"):
        load_frozen_policy(newer, tmp_path)


def test_unreadable_or_incomplete_files_are_reported_not_crashed_on(tmp_path: Path) -> None:
    with pytest.raises(PolicyConfigError, match="cannot be read"):
        load_frozen_policy(make_registry(), tmp_path)
    (tmp_path / SNAPSHOT_NAME).write_text("not json")
    with pytest.raises(PolicyConfigError, match="cannot be read"):
        load_frozen_policy(make_registry(), tmp_path)
    (tmp_path / SNAPSHOT_NAME).write_text('{"policy_version": "x"}')
    with pytest.raises(PolicyConfigError, match="cannot be read"):
        load_frozen_policy(make_registry(), tmp_path)


def test_sensitive_patterns_and_protected_branches_are_frozen_with_the_rest(tmp_path: Path) -> None:
    toml = '[sensitive]\npaths = ["vault/**"]\n[branches]\nprotected = ["trunk"]\n'
    original = effective(toml)
    freeze_policy(original, tmp_path, "1.2.3")

    frozen = load_frozen_policy(make_registry(), tmp_path)

    assert frozen.policy == original
    assert frozen.policy.sensitive_paths == ("vault/**",)
    assert frozen.policy.protected_branches == ("trunk",)


def test_editing_the_frozen_protected_branches_is_noticed(tmp_path: Path) -> None:
    freeze_policy(effective('[branches]\nprotected = ["trunk"]\n'), tmp_path, "1.2.3")
    path = tmp_path / SNAPSHOT_NAME
    path.write_bytes(path.read_bytes().replace(b'"trunk"', b'"nothing"'))

    with pytest.raises(PolicyConfigError, match="does not match its version"):
        load_frozen_policy(make_registry(), tmp_path)


def test_adapter_commands_are_frozen_with_the_rest(tmp_path: Path) -> None:
    original = effective('[adapters.python.commands]\ntest = ["uv", "run", "pytest"]\n')
    freeze_policy(original, tmp_path, "1.2.3")

    frozen = load_frozen_policy(make_registry(), tmp_path)

    assert frozen.policy == original
    assert frozen.policy.adapter_commands == {"python": {"test": ("uv", "run", "pytest")}}


def test_editing_a_frozen_adapter_command_is_noticed(tmp_path: Path) -> None:
    freeze_policy(effective('[adapters.python.commands]\ntest = ["pytest"]\n'), tmp_path, "1.2.3")
    path = tmp_path / SNAPSHOT_NAME
    path.write_bytes(path.read_bytes().replace(b'"pytest"', b'"evil"'))

    with pytest.raises(PolicyConfigError, match="does not match its version"):
        load_frozen_policy(make_registry(), tmp_path)


def test_redaction_settings_are_frozen_with_the_rest(tmp_path: Path) -> None:
    original = effective('[redaction]\nallow = ["x"]\npii = ["cpf"]\nentropy_threshold = 3.5\n')
    freeze_policy(original, tmp_path, "1.2.3")

    frozen = load_frozen_policy(make_registry(), tmp_path)

    assert frozen.policy == original
    assert frozen.policy.redaction.allow == ("x",)
    assert frozen.policy.redaction.entropy_threshold == 3.5


def test_weakening_the_frozen_redaction_by_hand_is_noticed(tmp_path: Path) -> None:
    freeze_policy(effective('[redaction]\npii = ["cpf", "email"]\n'), tmp_path, "1.2.3")
    path = tmp_path / SNAPSHOT_NAME
    path.write_bytes(path.read_bytes().replace(b'["cpf","email"]', b'["cpf"]'))

    with pytest.raises(PolicyConfigError, match="does not match its version"):
        load_frozen_policy(make_registry(), tmp_path)


def test_the_forbidden_licenses_are_frozen_with_the_rest(tmp_path: Path) -> None:
    original = effective('[licenses]\nforbidden = ["GPL-3.0-only"]\n')
    freeze_policy(original, tmp_path, "1.2.3")

    frozen = load_frozen_policy(make_registry(), tmp_path)

    assert frozen.policy == original
    assert frozen.policy.forbidden_licenses == ("GPL-3.0-only",)


def test_the_layers_are_frozen_in_their_order_and_come_back_the_same(tmp_path: Path) -> None:
    original = effective(
        '[[architecture.layers]]\nname = "cli"\npaths = ["src/cli"]\n'
        '[[architecture.layers]]\nname = "core"\npaths = ["src/core", "src/shared"]\n'
    )
    freeze_policy(original, tmp_path, "1.2.3")

    frozen = load_frozen_policy(make_registry(), tmp_path)

    assert frozen.policy == original
    assert [layer.name for layer in frozen.policy.architecture] == ["cli", "core"]
    assert frozen.version == original.version("1.2.3")
