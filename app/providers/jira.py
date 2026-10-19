"""Jira issues: each request is a list of JQL searches, and an issue found by more than one counts
once."""

import json
import urllib.request
from collections.abc import Sequence
from typing import Annotated

import msgspec

from app.types import NonEmpty, Table


class _Config(msgspec.Struct):
    base_url: NonEmpty
    api_version: int | str
    api_token: NonEmpty


class _Request(msgspec.Struct):
    jql: Annotated[tuple[NonEmpty, ...], msgspec.Meta(min_length=1)]


class _Issue(msgspec.Struct):
    id: str | int


class _Page(msgspec.Struct):
    issues: tuple[_Issue, ...] = ()
    total: int = 0


def count(provider: Table, requests: Sequence[Table]) -> int:
    config = msgspec.convert(provider, _Config)
    searches = [jql for request in requests for jql in msgspec.convert(request, _Request).jql]
    return len({issue for jql in searches for issue in _issue_ids(config, jql)})


def _issue_ids(config: _Config, jql: str) -> set[str]:
    """Page by page, until there are no more."""
    found: set[str] = set()
    start = 0
    while True:
        body = {"jql": jql, "fields": ["id"], "startAt": start, "maxResults": 100}
        request = urllib.request.Request(
            f"{config.base_url.rstrip('/')}/rest/api/{config.api_version}/search",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {config.api_token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(request) as response:
            page = msgspec.json.decode(response.read(), type=_Page)
        found.update(str(issue.id) for issue in page.issues)
        start += len(page.issues)
        if start >= page.total or not page.issues:
            return found
