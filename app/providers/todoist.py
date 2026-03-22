import argparse
import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Sequence
from typing import TypeAlias, TypedDict, cast

TODOIST_FILTER_URL = "https://api.todoist.com/api/v1/tasks/filter"
DEFAULT_FILTER = "today | overdue"
DEFAULT_PAGE_SIZE = 200


class TodoistTask(TypedDict):
    id: str
    priority: int
    content: str
    description: str


TodoistTasksResponse: TypeAlias = list[TodoistTask]


def parse_todoist_task(task: object) -> TodoistTask:
    if not isinstance(task, dict):
        raise TypeError("Task must be a JSON object")
    task = cast(dict[str, object], task)
    print(task)

    task_id = task.get("id")
    priority = task.get("priority")
    content = task.get("content")
    description = task.get("description", "")

    if not isinstance(task_id, str):
        raise TypeError("Task id must be a string")
    if not isinstance(priority, int):
        raise TypeError("Task priority must be an int")
    if not isinstance(content, str):
        raise TypeError("Task content must be a string")
    if not isinstance(description, str):
        raise TypeError("Task description must be a string")

    return TodoistTask(
        id=task_id,
        priority=priority,
        content=content,
        description=description,
    )


def parse_todoist_tasks(payload: dict[str, object]) -> list[TodoistTask]:
    results = payload.get("results")
    if not isinstance(results, list):
        raise TypeError("Expected results array in todoist response")
    results = cast(list[object], results)
    return [parse_todoist_task(item) for item in results]


def fetch_todoist_tasks(
    api_token: str, filter_value: str = DEFAULT_FILTER, lang: str = ""
) -> list[TodoistTask]:
    if not api_token:
        raise ValueError("api_token must be a non-empty string")
    if not filter_value:
        raise ValueError("filter_value must be a non-empty string")

    task_list: list[TodoistTask] = []
    cursor = None

    while True:
        params = {
            "query": filter_value,
            "limit": DEFAULT_PAGE_SIZE,
        }
        if cursor:
            params["cursor"] = cursor

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

        if not isinstance(payload, dict):
            raise RuntimeError("Todoist response must be a JSON object")
        payload = cast(dict[str, object], payload)

        task_list.extend(parse_todoist_tasks(payload))

        cursor = payload.get("next_cursor")
        if cursor is None:
            return task_list
        if not isinstance(cursor, str) or not cursor:
            raise RuntimeError("Todoist response contained an invalid next_cursor value")


def get_task_count(api_token: str, filter_value: str = DEFAULT_FILTER, lang: str = "") -> int:
    return len(fetch_todoist_tasks(api_token, filter_value=filter_value, lang=lang))


def parse_args(argv: Sequence[str] | None = None):
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


def main(argv: Sequence[str] | None = None):
    args = parse_args(argv)
    print(get_task_count(args.api_token, filter_value=args.filter_value, lang=args.lang))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
