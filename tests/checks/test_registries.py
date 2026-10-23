"""The registry lookups, against answers shaped as each registry's documentation says."""

import asyncio
import json
from datetime import UTC, datetime
from typing import Any

import pytest

from forja.checks.registries import Missing, Response, Standing, Unreachable, look_up


def serve(routes: dict[str, Any]) -> Any:
    """A fake ``get``: JSON (or text) for the known URLs, a status for ``int`` values, and no
    answer at all (unreachable) for the others."""

    async def get(url: str) -> Response | None:
        if url not in routes:
            return None
        found = routes[url]
        if isinstance(found, int):
            return Response(found, b"")
        body = found.encode() if isinstance(found, str) else json.dumps(found).encode()
        return Response(200, body)

    return get


def run(ecosystem: str, name: str, routes: dict[str, Any]) -> Standing:
    return asyncio.run(look_up(ecosystem, name, serve(routes)))


def at(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=UTC)


NPM = "https://registry.npmjs.org/left-pad"
COUNT = "https://api.npmjs.org/downloads/point/last-week/left-pad"


def test_npm_gives_the_creation_time_and_last_weeks_downloads() -> None:
    routes = {NPM: {"time": {"created": "2014-03-14T01:55:29.400Z"}}, COUNT: {"downloads": 7}}

    assert run("npm", "left-pad", routes) == Standing(at("2014-03-14T01:55:29.400"), 7)


def test_npm_scoped_names_keep_the_at_and_encode_the_slash() -> None:
    routes = {
        "https://registry.npmjs.org/@slack%2Fclient": {"time": {"created": "2016-01-01T00:00:00Z"}},
        "https://api.npmjs.org/downloads/point/last-week/@slack/client": {"downloads": 1},
    }

    assert run("npm", "@slack/client", routes).downloads == 1


def test_a_missing_package_is_missing_in_every_registry() -> None:
    cases = {
        "npm": NPM,
        "PyPI": "https://pypi.org/pypi/left-pad/json",
        "Go": "https://proxy.golang.org/left-pad/@v/list",
    }
    for ecosystem, url in cases.items():
        with pytest.raises(Missing):
            run(ecosystem, "left-pad", {url: 404})
    with pytest.raises(Missing):
        run("Go", "left-pad", {"https://proxy.golang.org/left-pad/@v/list": 410})


def test_a_registry_that_does_not_answer_or_errs_is_unreachable() -> None:
    with pytest.raises(Unreachable):
        run("npm", "left-pad", {})
    with pytest.raises(Unreachable):
        run("npm", "left-pad", {NPM: 500})
    with pytest.raises(Unreachable):
        run("npm", "left-pad", {NPM: "not json"})
    with pytest.raises(Unreachable):
        run("npm", "left-pad", {NPM: {"unexpected": 1}})
    with pytest.raises(Unreachable):
        run("npm", "left-pad", {NPM: {"time": {"created": "yesterday"}}, COUNT: {"downloads": 1}})
    with pytest.raises(Unreachable):
        run("nope", "x", {})


def test_pypi_normalizes_the_name_and_dates_the_earliest_upload_with_no_usage() -> None:
    routes = {
        "https://pypi.org/pypi/zope-interface/json": {
            "releases": {
                "1.0": [{"upload_time_iso_8601": "2020-05-01T10:00:00.5Z"}],
                "0.9": [{"upload_time_iso_8601": "2019-01-02T03:04:05Z"}],
                "0.1": [],
            }
        }
    }

    assert run("PyPI", "Zope.Interface", routes) == Standing(at("2019-01-02T03:04:05"), None)


def test_go_exists_when_the_proxy_lists_it_and_gives_neither_age_nor_usage() -> None:
    base = "https://proxy.golang.org/github.com/!burnt!sushi/toml"

    standing = run("Go", "github.com/BurntSushi/toml", {f"{base}/@v/list": "v1.1.0\nv1.0.0\n"})

    assert standing == Standing(None, None)  # the proxy's Time is the author's commit time
    assert run("Go", "github.com/BurntSushi/toml", {f"{base}/@v/list": ""}) == Standing(None, None)


@pytest.mark.parametrize(
    ("ecosystem", "name"),
    [
        ("npm", "../etc"),
        ("npm", "a/b"),
        ("npm", "@s/a/b"),
        ("npm", "a?x=1"),
        ("PyPI", "a/../b"),
        ("PyPI", "-a"),
        ("PyPI", "a b"),
        ("Go", "example.com/../x"),
        ("Go", "example.com//x"),
        ("Go", "/x"),
        ("Go", "x?y"),
        ("Maven", 'a" OR g:"b:c'),
        ("Maven", "a:b:c"),
        ("Maven", "ab"),
        ("NuGet", "a/b"),
        ("NuGet", "a%2fb"),
    ],
)
def test_a_name_the_registry_could_not_hold_is_missing_and_never_reaches_a_url(
    ecosystem: str, name: str
) -> None:
    async def never(url: str) -> Response | None:
        raise AssertionError(url)

    with pytest.raises(Missing):
        asyncio.run(look_up(ecosystem, name, never))


MAVEN = (
    "https://search.maven.org/solrsearch/select?"
    "q=g%3A%22com.google.inject%22%20AND%20a%3A%22guice%22&core=gav&rows=200&start=0&wt=json"
)


def test_maven_dates_the_earliest_version_and_an_empty_answer_is_missing() -> None:
    docs = [{"timestamp": 1_600_000_000_000}, {"timestamp": 1_500_000_000_000}]
    found = {MAVEN: {"response": {"numFound": 2, "docs": docs}}}

    standing = run("Maven", "com.google.inject:guice", found)

    assert standing == Standing(datetime.fromtimestamp(1_500_000_000, UTC), None)
    with pytest.raises(Missing):
        run("Maven", "com.google.inject:guice", {MAVEN: {"response": {"numFound": 0, "docs": []}}})


INDEX = "https://api.nuget.org/v3/index.json"
SERVICES = {
    "resources": [
        {"@id": "https://reg/", "@type": "RegistrationsBaseUrl/3.6.0"},
        {"@id": "https://search/query", "@type": "SearchQueryService/3.5.0"},
    ]
}


def test_nuget_dates_the_earliest_listed_version_and_counts_total_downloads() -> None:
    leaf = {"catalogEntry": {"published": "2019-01-01T00:00:00+00:00"}}
    unlisted = {"catalogEntry": {"published": "1900-01-01T00:00:00+00:00"}}
    routes = {
        INDEX: SERVICES,
        "https://reg/newtonsoft.json/index.json": {
            "items": [
                {"@id": "https://reg/page/1", "items": [leaf, unlisted]},
                {"@id": "https://reg/page/2"},
            ]
        },
        "https://reg/page/2": {
            "items": [{"catalogEntry": {"published": "2021-05-05T05:05:05+00:00"}}]
        },
        "https://search/query?q=Newtonsoft.Json&take=20&prerelease=true": {
            "data": [
                {"id": "Other", "totalDownloads": 1},
                {"id": "Newtonsoft.Json", "totalDownloads": 12345},
            ]
        },
    }

    standing = run("NuGet", "Newtonsoft.Json", routes)

    assert standing == Standing(at("2019-01-01T00:00:00"), 12345)


def test_nuget_without_a_matching_search_hit_has_no_download_count() -> None:
    routes = {
        INDEX: SERVICES,
        "https://reg/x/index.json": {
            "items": [{"items": [{"catalogEntry": {"published": "2019-01-01T00:00:00Z"}}]}]
        },
        "https://search/query?q=X&take=20&prerelease=true": {"data": []},
    }

    assert run("NuGet", "X", routes).downloads is None


def test_nuget_missing_package_is_missing_and_a_service_index_without_it_is_unreachable() -> None:
    with pytest.raises(Missing):
        run("NuGet", "x", {INDEX: SERVICES, "https://reg/x/index.json": 404})
    with pytest.raises(Unreachable):
        run("NuGet", "x", {INDEX: {"resources": []}})


def test_maven_reads_every_page_of_versions_to_find_the_oldest() -> None:
    base = "https://search.maven.org/solrsearch/select?q=g%3A%22g%22%20AND%20a%3A%22a%22&core=gav"
    newer = {"response": {"numFound": 201, "docs": [{"timestamp": 2_000_000_000_000}] * 200}}
    oldest = {"response": {"numFound": 201, "docs": [{"timestamp": 1_000_000_000_000}]}}
    routes = {
        f"{base}&rows=200&start=0&wt=json": newer,
        f"{base}&rows=200&start=200&wt=json": oldest,
    }

    standing = run("Maven", "g:a", routes)

    assert standing == Standing(datetime.fromtimestamp(1_000_000_000, UTC), None)
