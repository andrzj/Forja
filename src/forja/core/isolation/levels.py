"""Isolation levels and what each one really guarantees (contract 3).

The table is data, transcribed from the spec, so the same source feeds the declaration made to the
user, the evidence and the PR text. "Detected only" means the spec promises detection after the
fact, not prevention; in this increment no detector exists, so those rows read "not verified".
"""

from collections.abc import Mapping
from enum import StrEnum
from types import MappingProxyType

from pydantic import BaseModel, ConfigDict

from forja.core.artifacts.models import NonEmpty


class IsolationLevel(StrEnum):
    WSL = "wsl"
    REDUCED = "reduced"


class Guarantee(StrEnum):
    READ_RESTRICTED_TO_WORKCOPY = "read_restricted_to_workcopy"
    NETWORK_ALLOWLIST = "network_allowlist"
    NO_GIT_AVAILABLE = "no_git_available"
    NO_SECRETS = "no_secrets"
    NO_DOT_GIT_IN_COPY = "no_dot_git_in_copy"
    SENSITIVE_FILES_ABSENT = "sensitive_files_absent"
    FILTERED_ENVIRONMENT = "filtered_environment"
    PROCESS_TREE_CONTAINED = "process_tree_contained"


class Status(StrEnum):
    ENFORCED = "enforced"  # made impossible during the run
    DETECTED_ONLY = "detected_only"  # only noticed afterwards; not verified yet
    NOT_ENFORCED = "not_enforced"


G = Guarantee

# Level -> guarantees enforced during the run.
ENFORCED: Mapping[IsolationLevel, frozenset[Guarantee]] = MappingProxyType(
    {
        IsolationLevel.WSL: frozenset(Guarantee),
        IsolationLevel.REDUCED: frozenset(
            {
                G.FILTERED_ENVIRONMENT,
                G.SENSITIVE_FILES_ABSENT,
                G.NO_DOT_GIT_IN_COPY,
                G.PROCESS_TREE_CONTAINED,
            }
        ),
    }
)

# Level -> guarantees that are only detected afterwards.
DETECTED_ONLY: Mapping[IsolationLevel, frozenset[Guarantee]] = MappingProxyType(
    {
        IsolationLevel.WSL: frozenset(),
        IsolationLevel.REDUCED: frozenset(
            {G.READ_RESTRICTED_TO_WORKCOPY, G.NETWORK_ALLOWLIST, G.NO_GIT_AVAILABLE}
        ),
    }
)


def status_of(level: IsolationLevel, guarantee: Guarantee) -> Status:
    if guarantee in ENFORCED[level]:
        return Status.ENFORCED
    if guarantee in DETECTED_ONLY[level]:
        return Status.DETECTED_ONLY
    return Status.NOT_ENFORCED


class Context(StrEnum):
    AGENT = "agent"  # where the CLI of the agent runs
    REPO_CODE = "repo_code"  # where build, tests and tools of the repository run


class IsolationRecord(BaseModel):
    """The levels in force for this run, recorded when the user confirms.

    The two contexts usually match; they differ when a repository can only build on Windows, so
    its tools run reduced while the agent stays in WSL.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    agent: IsolationLevel
    repo_code: IsolationLevel
    notes: tuple[NonEmpty, ...] = ()

    def level_of(self, context: Context) -> IsolationLevel:
        return self.agent if context is Context.AGENT else self.repo_code

    def declaration(self) -> dict[Context, dict[Guarantee, Status]]:
        """Every guarantee with its status, per context: the text of the PR declaration."""
        return {
            context: {g: status_of(self.level_of(context), g) for g in Guarantee}
            for context in Context
        }

    @property
    def is_reduced(self) -> bool:
        return IsolationLevel.REDUCED in (self.agent, self.repo_code)
