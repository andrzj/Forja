class ArtifactError(Exception):
    """Base for every problem with stored artifacts."""


class ArtifactMissing(ArtifactError):
    """A referenced header or blob is not in the store; the stage that made it must be redone."""

    def __init__(self, artifact_id: str, what: str) -> None:
        self.artifact_id = artifact_id
        self.what = what
        super().__init__(f"artifact {artifact_id!r}: {what} is missing")


class ArtifactCorrupt(ArtifactError):
    """Stored bytes do not match their hash or do not fit the schema."""

    def __init__(self, artifact_id: str, reason: str) -> None:
        self.artifact_id = artifact_id
        self.reason = reason
        super().__init__(f"artifact {artifact_id!r} is corrupt: {reason}")


class ArtifactExists(ArtifactError):
    """The id is taken by a different artifact."""


class InputMismatch(ArtifactError):
    """A declared input is not in the store or has another hash than declared."""


class SchemaNotDefined(ArtifactError):
    """No body schema exists yet for this artifact type."""


class UnsupportedArtifactVersion(ArtifactError):
    """The artifact was written by a newer Forja; reading it could silently misread it."""

    def __init__(self, artifact_id: str, version: int, supported: int) -> None:
        super().__init__(
            f"artifact {artifact_id!r} has schema version {version}, newer than the supported "
            f"{supported}; upgrade Forja to read it"
        )


class InvalidLlmOutput(ArtifactError):
    """The model's answer breaks the output contract; ``problems`` can be fed back to it."""

    def __init__(self, problems: list[str]) -> None:
        self.problems = problems
        super().__init__("invalid LLM output: " + "; ".join(problems))
