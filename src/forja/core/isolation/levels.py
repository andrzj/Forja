"""What the Forja guarantees about where code runs, and what it leaves to the environment.

The Forja runs in the terminal where the person is. Building a sandbox is not its job: whoever
runs it is responsible for the infrastructure and the permissions around it (a corporate machine,
a container, a virtual machine, a plain workstation), and says so by choosing where to run. What
the Forja itself imposes works on any system and needs nothing installed. The table is data, so
the same source feeds the declaration made to the person, the evidence and the summary.
"""

from collections.abc import Mapping
from enum import StrEnum
from types import MappingProxyType

from pydantic import BaseModel, ConfigDict

from forja.core.artifacts.models import NonEmpty


class IsolationLevel(StrEnum):
    ENVIRONMENT = "environment"  # the person's own environment; the Forja adds its own measures


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
    ENFORCED = "enforced"  # made impossible by the Forja during the run
    DETECTED_ONLY = "detected_only"  # only noticed afterwards by the Forja
    ENVIRONMENT = "environment"  # up to the environment the person chose to run in


G = Guarantee

# Level -> guarantees the Forja makes impossible during the run.
ENFORCED: Mapping[IsolationLevel, frozenset[Guarantee]] = MappingProxyType(
    {
        IsolationLevel.ENVIRONMENT: frozenset(
            {
                G.FILTERED_ENVIRONMENT,
                G.SENSITIVE_FILES_ABSENT,
                G.NO_DOT_GIT_IN_COPY,
                G.PROCESS_TREE_CONTAINED,
            }
        ),
    }
)

# Level -> guarantees the Forja only notices afterwards (git is snapshotted around every call).
DETECTED_ONLY: Mapping[IsolationLevel, frozenset[Guarantee]] = MappingProxyType(
    {IsolationLevel.ENVIRONMENT: frozenset({G.NO_GIT_AVAILABLE})}
)


def status_of(level: IsolationLevel, guarantee: Guarantee) -> Status:
    if guarantee in ENFORCED[level]:
        return Status.ENFORCED
    if guarantee in DETECTED_ONLY[level]:
        return Status.DETECTED_ONLY
    return Status.ENVIRONMENT


class Context(StrEnum):
    AGENT = "agent"  # where the CLI of the agent runs
    REPO_CODE = "repo_code"  # where build, tests and tools of the repository run


class IsolationRecord(BaseModel):
    """The level in force for this run, recorded when the person confirms."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    agent: IsolationLevel
    repo_code: IsolationLevel
    notes: tuple[NonEmpty, ...] = ()

    def level_of(self, context: Context) -> IsolationLevel:
        return self.agent if context is Context.AGENT else self.repo_code

    def declaration(self) -> dict[Context, dict[Guarantee, Status]]:
        """Every guarantee with its status, per context: the text of the declaration."""
        return {
            context: {g: status_of(self.level_of(context), g) for g in Guarantee}
            for context in Context
        }
