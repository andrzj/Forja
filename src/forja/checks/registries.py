"""What the official package registries say about a package: that it exists, since when, and how
much it is used.

Each lookup follows the registry's own documentation:

- npm: the package document at ``registry.npmjs.org/<name>`` has ``time.created`` (npm/registry,
  ``docs/REGISTRY-API.md``); downloads are ``api.npmjs.org/downloads/point/last-week/<name>``,
  field ``downloads`` (``docs/download-counts.md``).
- PyPI: ``pypi.org/pypi/<project>/json``, files under ``releases`` carry ``upload_time_iso_8601``
  (docs.pypi.org/api/json); the project name is normalized as PEP 503 says. PyPI gives no download
  count (the field is always -1), so usage is not measured.
- Go: the module proxy protocol (go.dev/ref/mod#goproxy-protocol): ``$module/@v/list``,
  ``@v/$version.info`` and ``@latest``, with ``Time``; the module path is case-encoded. No usage.
- Maven Central: the search API (central.sonatype.org/search/rest-api-guide), ``core=gav`` lists
  the versions of ``g:`` and ``a:``. The guide does not name the response fields;
  ``response.numFound`` and ``response.docs[].timestamp`` (milliseconds) are used and must be
  confirmed against the real service. No usage.
- NuGet: the service index (``api.nuget.org/v3/index.json``) gives the ``RegistrationsBaseUrl`` and
  the ``SearchQueryService``; the registration index lists the versions with ``published``, and
  the search result has ``totalDownloads`` (learn.microsoft.com/nuget/api).

The documentation does not say what each registry answers for a package that does not exist; a
404 (410 for Go, which the protocol names) is taken to mean that, and only the real run can confirm.
"""

import asyncio
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

TIMEOUT = 20.0
NPM, PYPI, GO, MAVEN, NUGET = "npm", "PyPI", "Go", "Maven", "NuGet"
NOT_FOUND = frozenset({404, 410})
NUGET_INDEX = "https://api.nuget.org/v3/index.json"
UNLISTED = 1900  # nuget.org sets ``published`` to this year for an unlisted package
GO_VERSIONS_LOOKED_AT = 10


@dataclass(frozen=True)
class Response:
    status: int
    body: bytes


HttpGet = Callable[[str], Awaitable[Response | None]]  # None: the registry could not be reached


@dataclass(frozen=True)
class Standing:
    """What a registry says about a package that exists."""

    first_published: datetime | None  # None: the registry did not say
    downloads: int | None  # None: the registry gives no count


class Missing(Exception):
    """The registry has no such package."""


class Unreachable(Exception):
    """The registry did not answer, or answered with something that is not what it documents."""


def _fetch(url: str) -> Response | None:
    if not url.startswith("https://"):
        return None
    request = urllib.request.Request(  # noqa: S310 - https only, checked above
        url, headers={"User-Agent": "forja", "Accept": "application/json"}
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as answer:  # noqa: S310
            return Response(answer.status, answer.read())
    except urllib.error.HTTPError as error:
        return Response(error.code, b"")
    except (urllib.error.URLError, TimeoutError, OSError):
        return None


async def urllib_get(url: str) -> Response | None:
    return await asyncio.to_thread(_fetch, url)


async def _get(get: HttpGet, url: str) -> Response:
    answer = await get(url)
    if answer is None:
        raise Unreachable(url)
    if answer.status in NOT_FOUND:
        raise Missing(url)
    if answer.status != 200:
        raise Unreachable(f"{url} answered {answer.status}")
    return answer


async def _json(get: HttpGet, url: str) -> Any:
    try:
        return json.loads((await _get(get, url)).body)
    except ValueError:
        raise Unreachable(f"{url} did not answer with JSON") from None


def _when(value: object) -> datetime:
    try:
        moment = datetime.fromisoformat(str(value))
    except ValueError:
        raise Unreachable(f"unreadable date {value!r}") from None
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


async def look_up(ecosystem: str, name: str, get: HttpGet) -> Standing:
    """The standing of ``name`` in the official registry of ``ecosystem``."""
    try:
        match ecosystem:
            case "npm":
                return await _npm(name, get)
            case "PyPI":
                return await _pypi(name, get)
            case "Go":
                return await _go(name, get)
            case "Maven":
                return await _maven(name, get)
            case "NuGet":
                return await _nuget(name, get)
    except (KeyError, TypeError, AttributeError, IndexError):
        raise Unreachable(
            f"{ecosystem}: the answer for {name} is not what the registry documents"
        ) from None
    raise Unreachable(f"no registry is known for {ecosystem}")


async def _npm(name: str, get: HttpGet) -> Standing:
    document = await _json(get, f"https://registry.npmjs.org/{urllib.parse.quote(name, safe='@')}")
    created = _when(document["time"]["created"])
    counts = await _json(get, f"https://api.npmjs.org/downloads/point/last-week/{name}")
    return Standing(created, int(counts["downloads"]))


def _pep_503(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


async def _pypi(name: str, get: HttpGet) -> Standing:
    document = await _json(get, f"https://pypi.org/pypi/{_pep_503(name)}/json")
    uploads = [
        _when(file["upload_time_iso_8601"])
        for files in document["releases"].values()
        for file in files
    ]
    return Standing(min(uploads, default=None), None)


def _case_encoded(module: str) -> str:
    return "".join(f"!{c.lower()}" if c.isupper() else c for c in module)


async def _go(module: str, get: HttpGet) -> Standing:
    base = f"https://proxy.golang.org/{_case_encoded(module)}"
    listing = (await _get(get, f"{base}/@v/list")).body.decode("utf-8", errors="replace")
    versions = [line.strip() for line in listing.splitlines() if line.strip()]
    moments = []
    for version in versions[:GO_VERSIONS_LOOKED_AT]:
        info = await _json(get, f"{base}/@v/{_case_encoded(version)}.info")
        if "Time" in info:
            moments.append(_when(info["Time"]))
    if not moments:  # no tagged version: the latest (pseudo-)version still dates the module
        info = await _json(get, f"{base}/@latest")
        if "Time" in info:
            moments.append(_when(info["Time"]))
    return Standing(min(moments, default=None), None)


async def _maven(coordinates: str, get: HttpGet) -> Standing:
    group, _, artifact = coordinates.partition(":")
    query = urllib.parse.quote(f'g:"{group}" AND a:"{artifact}"')
    url = f"https://search.maven.org/solrsearch/select?q={query}&core=gav&rows=200&wt=json"
    found = (await _json(get, url))["response"]
    if int(found["numFound"]) == 0:
        raise Missing(coordinates)
    stamps = [datetime.fromtimestamp(int(doc["timestamp"]) / 1000, UTC) for doc in found["docs"]]
    return Standing(min(stamps, default=None), None)


async def _nuget_resource(get: HttpGet, kind: str) -> str:
    index = await _json(get, NUGET_INDEX)
    for resource in index["resources"]:
        if str(resource["@type"]).startswith(kind):
            return str(resource["@id"])
    raise Unreachable(f"the NuGet service index has no {kind}")


async def _nuget(name: str, get: HttpGet) -> Standing:
    base = await _nuget_resource(get, "RegistrationsBaseUrl")
    index = await _json(get, f"{base.rstrip('/')}/{name.lower()}/index.json")
    published = []
    for page in index["items"]:
        leaves = page.get("items")
        if leaves is None:
            leaves = (await _json(get, str(page["@id"])))["items"]
        for leaf in leaves:
            moment = _when(leaf["catalogEntry"]["published"])
            if moment.year != UNLISTED:
                published.append(moment)
    search = await _nuget_resource(get, "SearchQueryService")
    url = f"{search}?q={urllib.parse.quote(name)}&take=20&prerelease=true"
    hits = [
        hit for hit in (await _json(get, url))["data"] if str(hit["id"]).lower() == name.lower()
    ]
    downloads = int(hits[0]["totalDownloads"]) if hits and "totalDownloads" in hits[0] else None
    return Standing(min(published, default=None), downloads)
