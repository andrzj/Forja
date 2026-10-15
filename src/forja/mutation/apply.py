"""Make the mutant: the file with one site changed."""

from forja.mutation.model import Site


def apply_site(source: str, site: Site) -> str:
    """The source with ``site`` changed. Refuses a site that does not belong to this source."""
    data = source.encode("utf-8")
    if data[site.start : site.end] != site.original.encode("utf-8"):
        raise ValueError(f"line {site.line}: the source no longer has {site.original!r} there")
    return (data[: site.start] + site.mutant.encode("utf-8") + data[site.end :]).decode("utf-8")
