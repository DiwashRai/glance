import argparse
import json
import urllib.error
import urllib.parse
import urllib.request


TODOIST_FILTER_URL = "https://api.todoist.com/api/v1/tasks/filter"
DEFAULT_FILTER = "today | overdue"
DEFAULT_PAGE_SIZE = 200


def fetch_todoist_task_ids(api_token, filter_value=DEFAULT_FILTER, lang=None):
    if not isinstance(api_token, str) or not api_token:
        raise ValueError("api_token must be a non-empty string")
    if not isinstance(filter_value, str) or not filter_value:
        raise ValueError("filter_value must be a non-empty string")
    if lang is not None and (not isinstance(lang, str) or not lang):
        raise ValueError("lang must be a non-empty string when provided")

    task_ids = set()
    cursor = None

    while True:
        params = {
            "query": filter_value,
            "limit": DEFAULT_PAGE_SIZE,
        }
        if cursor:
            params["cursor"] = cursor
        if lang:
            params["lang"] = lang

        url = f"{TODOIST_FILTER_URL}?{urllib.parse.urlencode(params)}"
        request = urllib.request.Request(
            url,
            headers={"Authorization": f"Bearer {api_token}"},
            method="GET",
        )

        try:
            with urllib.request.urlopen(request) as response:
                payload = json.load(response)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace").strip()
            raise RuntimeError(
                f"Todoist request failed with HTTP {exc.code}: {detail or exc.reason}"
            ) from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Todoist request failed: {exc.reason}") from exc

        results = payload.get("results", [])
        if not isinstance(results, list):
            raise RuntimeError("Todoist response did not contain a results list")

        for task in results:
            if not isinstance(task, dict):
                continue
            task_id = task.get("id")
            if task_id is not None:
                task_ids.add(str(task_id))

        cursor = payload.get("next_cursor")
        if cursor is None:
            return task_ids
        if not isinstance(cursor, str) or not cursor:
            raise RuntimeError("Todoist response contained an invalid next_cursor value")


def get_task_count(api_token, filter_value=DEFAULT_FILTER, lang=None):
    return len(fetch_todoist_task_ids(api_token, filter_value=filter_value, lang=lang))


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Return active Todoist task counts for a filter query."
    )
    parser.add_argument("api_token", help="Todoist API token.")
    parser.add_argument(
        "--filter",
        dest="filter_value",
        default=DEFAULT_FILTER,
        help="Todoist filter string. Defaults to today's active tasks.",
    )
    parser.add_argument(
        "--lang",
        help="Optional filter language if not using the default Todoist account language.",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    print(get_task_count(args.api_token, filter_value=args.filter_value, lang=args.lang))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
