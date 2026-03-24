import json
import urllib.request
from collections.abc import Sequence
from typing import ClassVar

from app.providers.registry import provider_registry
from app.types import ProviderContext


def fetch_jira_query_issue_ids(base_url: str, api_version: int | str, token: str, jql: str):
    issue_ids: set[str] = set()
    start_at = 0

    while True:
        payload = json.dumps(
            {
                "jql": jql,
                "fields": ["id"],
                "startAt": start_at,
                "maxResults": 100,
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            f"{base_url.rstrip('/')}/rest/api/{api_version}/search",
            data=payload,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        with urllib.request.urlopen(request) as response:
            result = json.load(response)

        issues = result.get("issues", [])
        for issue in issues:
            issue_id = issue.get("id")
            if issue_id is not None:
                issue_ids.add(str(issue_id))

        total = int(result.get("total", 0))
        start_at += len(issues)
        if start_at >= total or not issues:
            return issue_ids


def get_issue_count(base_url: str, api_version: int | str, token: str, jqls: Sequence[str]) -> int:
    issue_ids: set[str] = set()
    for jql in jqls:
        issue_ids.update(fetch_jira_query_issue_ids(base_url, api_version, token, jql))
    return len(issue_ids)


def _parse_jira_input(ctx: ProviderContext) -> tuple[str, int | str, str, list[str]]:
    base_url = ctx.provider_config.get("base_url")
    if not isinstance(base_url, str) or not base_url:
        raise ValueError(f"[providers.{ctx.provider_name}].base_url must be a non-empty string")

    api_version = ctx.provider_config.get("api_version")
    if not isinstance(api_version, (int, str)) or not str(api_version):
        raise ValueError(f"[providers.{ctx.provider_name}].api_version must be set")

    api_token = ctx.provider_config.get("api_token")
    if not isinstance(api_token, str) or not api_token:
        raise ValueError(f"[providers.{ctx.provider_name}].api_token must be a non-empty string")

    jqls: list[str] = []
    for request in ctx.requests:
        jql = request.get("jql")
        if not isinstance(jql, list) or not jql:
            raise ValueError("Jira requests require a non-empty 'jql' list")

        for item in jql:
            if not isinstance(item, str) or not item:
                raise ValueError("Jira jql items must be non-empty strings")
            jqls.append(item)

    return base_url, api_version, api_token, jqls


class JiraProvider:
    kind: ClassVar[str] = "jira"

    def count(self, ctx: ProviderContext) -> int:
        base_url, api_version, api_token, jqls = _parse_jira_input(ctx)
        return get_issue_count(base_url, api_version, api_token, jqls)


provider_registry.register(JiraProvider)
