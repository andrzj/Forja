from importlib.metadata import PackageNotFoundError, version


def forja_version() -> str:
    """Installed version of Forja; ``0.0.0`` when running from a source tree without install."""
    try:
        return version("forja")
    except PackageNotFoundError:
        return "0.0.0"
