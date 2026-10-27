"""The policy frozen into the run directory when the user confirms.

From then on the run reads this file and ignores later edits to any TOML, so resuming judges
with exactly the policy the run started with.
"""

import json
from dataclasses import dataclass
from pathlib import Path

from forja.core.atomic import atomic_write_bytes
from forja.core.events.models import canonical_json
from forja.core.policy.config import (
    EffectivePolicy,
    Layer,
    PolicyConfigError,
    build_policy,
)
from forja.core.policy.registry import CheckRegistry

SNAPSHOT_NAME = "policy.json"


@dataclass(frozen=True)
class FrozenPolicy:
    policy: EffectivePolicy
    version: str


def freeze_policy(policy: EffectivePolicy, run_dir: Path, forja_version: str) -> str:
    """Write ``policy.json`` atomically and return the policy version it carries."""
    version = policy.version(forja_version)
    document = {"policy_version": version, "policy": policy.to_dict()}
    atomic_write_bytes(run_dir / SNAPSHOT_NAME, canonical_json(document))
    return version


def load_frozen_policy(registry: CheckRegistry, run_dir: Path) -> FrozenPolicy:
    """Read the frozen policy back, refusing a file that was edited or no longer fits the code."""
    path = run_dir / SNAPSHOT_NAME
    try:
        document = json.loads(path.read_bytes())
        stored_version = document["policy_version"]
        frozen = document["policy"]
        layer = Layer(
            "frozen policy",
            {
                "checks": frozen["checks"],
                "sensitive": frozen["sensitive"],
                "branches": frozen["branches"],
                "adapters": frozen["adapters"],
                "redaction": frozen["redaction"],
                **({"licenses": frozen["licenses"]} if "licenses" in frozen else {}),
                **({"voice": frozen["voice"]} if "voice" in frozen else {}),
                **({"architecture": frozen["architecture"]} if "architecture" in frozen else {}),
                **({"differential": frozen["differential"]} if "differential" in frozen else {}),
            },
        )
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise PolicyConfigError([f"frozen policy {path} cannot be read: {error}"]) from None
    policy = build_policy(registry, [layer])
    forja_version = stored_version.rsplit("+", 1)[0]
    if policy.version(forja_version) != stored_version:
        raise PolicyConfigError(
            [
                f"frozen policy {path} does not match its version {stored_version}: the file was "
                "edited, or the checks it refers to changed since the run started"
            ]
        )
    return FrozenPolicy(policy, stored_version)
