import re
from collections.abc import Iterator
from dataclasses import dataclass

from forja.core.gates.effects import CheckSettings
from forja.core.gates.models import InconclusivePolicy, Mode

LANGUAGES = frozenset({"java", "go", "python", "csharp", "javascript", "typescript"})
_CHECK_ID = re.compile(r"^[a-z][a-z0-9_]*$")


@dataclass(frozen=True)
class CheckSpec:
    """What the policy may say about one check, and what it says when left alone.

    Predicates live in code; the configuration only sets values. ``thresholds``, ``commands`` and
    ``limits`` are the names a configuration is allowed to set for this check. A check that starts
    in observation (new, or without calibration data) is promoted by an explicit, recorded decision.
    """

    id: str
    gate: int
    default_mode: Mode
    default_on_inconclusive: InconclusivePolicy | None = None
    thresholds: frozenset[str] = frozenset()
    commands: frozenset[str] = frozenset()
    limits: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        if not _CHECK_ID.fullmatch(self.id):
            raise ValueError(f"invalid check id {self.id!r}")
        if self.gate < 1:
            raise ValueError(f"check {self.id!r}: gate numbers start at 1")
        CheckSettings(self.default_mode, self.default_on_inconclusive)  # validates the pair

    @property
    def default_settings(self) -> CheckSettings:
        return CheckSettings(self.default_mode, self.default_on_inconclusive)


class CheckRegistry:
    def __init__(self) -> None:
        self._specs: dict[str, CheckSpec] = {}

    def register(self, spec: CheckSpec) -> None:
        if spec.id in self._specs:
            raise ValueError(f"check {spec.id!r} is already registered")
        self._specs[spec.id] = spec

    def get(self, check_id: str) -> CheckSpec:
        return self._specs[check_id]

    def __contains__(self, check_id: object) -> bool:
        return check_id in self._specs

    def __iter__(self) -> Iterator[CheckSpec]:
        return iter(self._specs.values())
