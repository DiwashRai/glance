import json
import urllib.request


def fetch_jira_query_issue_ids(base_url, api_version, token, jql):
    issue_ids = set()
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


def get_issue_count(base_url, api_version, token, jqls):
    issue_ids = set()
    for jql in jqls:
        issue_ids.update(fetch_jira_query_issue_ids(base_url, api_version, token, jql))
    return len(issue_ids)
