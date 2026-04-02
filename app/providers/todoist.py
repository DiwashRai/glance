import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Sequence
from dataclasses import dataclass
from typing import ClassVar, TypeAlias, cast

from app.providers.registry import provider_registry
from app.types import ProviderContext, TimeBlockRow, is_str_list

TODOIST_FILTER_URL = "https://api.todoist.com/api/v1/tasks/filter"
DEFAULT_PAGE_SIZE = 200
MAX_PAGES = 10
MAX_RETRIES = 5
DEFAULT_TIME_BLOCK_COLOR = "white"
COLOR_LABEL_PREFIX = "color:"
logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class TodoistTask:
    id: str
    priority: int
    content: str
    description: str
    labels: list[str]
    due: str | None
    duration: int | None


TodoistTasksResponse: TypeAlias = list[TodoistTask]


def parse_todoist_due(raw: object) -> str | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise TypeError("Task due must be a JSON object")
    raw = cast(dict[str, object], raw)

    date = raw.get("date")

    if not isinstance(date, str):
        raise TypeError("Task due.date must be a string")

    return date


def parse_todoist_duration(raw: object) -> int | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise TypeError("Task duration must be a JSON object")
    raw = cast(dict[str, object], raw)

    amount = raw.get("amount")
    unit = raw.get("unit")
    if not isinstance(amount, int):
        raise TypeError("Task duration.amount must be an int")
    if not isinstance(unit, str):
        raise TypeError("Task duration.unit must be a string")
    if unit != "minute":
        raise RuntimeError("unit expected to be 'minute'. API changed?")

    return amount


def parse_todoist_task(task: object) -> TodoistTask:
    if not isinstance(task, dict):
        raise TypeError("Task must be a JSON object")
    task = cast(dict[str, object], task)

    task_id = task.get("id")
    priority = task.get("priority")
    content = task.get("content")
    description = task.get("description", "")
    labels = task.get("labels", [])
    due = task.get("due")
    duration = task.get("duration")

    if not isinstance(task_id, str):
        raise TypeError("Task id must be a string")
    if not isinstance(priority, int):
        raise TypeError("Task priority must be an int")
    if not isinstance(content, str):
        raise TypeError("Task content must be a string")
    if not isinstance(description, str):
        raise TypeError("Task description must be a string")
    if not is_str_list(labels):
        raise TypeError("Task labels must be a list of strings")

    due = parse_todoist_due(due)
    duration = parse_todoist_duration(duration)

    return TodoistTask(
        id=task_id,
        priority=priority,
        content=content,
        description=description,
        labels=labels,
        due=due,
        duration=duration,
    )


def parse_todoist_tasks(payload: dict[str, object]) -> list[TodoistTask]:
    results = payload.get("results")
    if not isinstance(results, list):
        raise TypeError("Expected results array in todoist response")
    results = cast(list[object], results)
    return [parse_todoist_task(item) for item in results]


def fetch_todoist_tasks(api_token: str, filter_value: str, lang: str = "") -> list[TodoistTask]:
    if not api_token:
        raise ValueError("api_token must be a non-empty string")
    if not filter_value:
        raise ValueError("filter_value must be a non-empty string")

    task_list: list[TodoistTask] = []
    cursor = None

    for _ in range(MAX_PAGES):
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

        payload = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                with urllib.request.urlopen(request) as response:
                    payload = json.load(response)
                break
            except urllib.error.HTTPError as exc:
                if exc.code in (502, 503) and attempt < MAX_RETRIES:
                    delay = min(2**attempt, 8)
                    logger.warning(
                        f"Todoist request failed with HTTP {exc.code}: {exc.reason}. "
                        f"Retrying in {delay}s (attempt {attempt + 2}/{MAX_RETRIES + 1})"
                    )
                    time.sleep(delay)
                    continue
                detail = exc.read().decode("utf-8", errors="replace").strip()
                raise RuntimeError(
                    f"Todoist request failed with HTTP {exc.code}: {detail or exc.reason}"
                ) from exc

        if not isinstance(payload, dict):
            raise RuntimeError("Todoist response must be a JSON object")
        payload = cast(dict[str, object], payload)

        task_list.extend(parse_todoist_tasks(payload))

        cursor = payload.get("next_cursor")
        if cursor is None:
            break
        if not isinstance(cursor, str) or not cursor:
            raise RuntimeError("Todoist response contained an invalid next_cursor value")

    return task_list


def get_task_count(api_token: str, filter_values: Sequence[str], lang: str = "") -> int:
    task_ids: set[str] = set()
    for filter_value in filter_values:
        for task in fetch_todoist_tasks(api_token, filter_value=filter_value, lang=lang):
            task_ids.add(task.id)
    return len(task_ids)


def get_time_block_color(labels: Sequence[str]) -> str:
    for label in labels:
        if not label.lower().startswith(COLOR_LABEL_PREFIX):
            continue
        color_value = label[len(COLOR_LABEL_PREFIX) :].strip()
        if not color_value:
            continue
        return color_value
    return DEFAULT_TIME_BLOCK_COLOR


def get_time_blocks(
    api_token: str, filter_values: Sequence[str], lang: str = ""
) -> list[TimeBlockRow]:
    seen_task_ids: set[str] = set()
    rows: list[TimeBlockRow] = []

    for filter_value in filter_values:
        for task in fetch_todoist_tasks(api_token, filter_value=filter_value, lang=lang):
            if task.id in seen_task_ids:
                continue
            seen_task_ids.add(task.id)

            if task.due is None or task.duration is None:
                continue

            rows.append(
                TimeBlockRow(
                    task.content,
                    task.due,
                    task.duration,
                    get_time_block_color(task.labels),
                )
            )

    rows.sort(key=lambda row: (row.due, row.duration))
    logger.info(rows)
    return rows


def _parse_todoist_input(ctx: ProviderContext) -> tuple[str, list[str], str]:
    api_token = ctx.provider_config.get("api_token")
    if not isinstance(api_token, str) or not api_token:
        raise ValueError(f"[providers.{ctx.provider_name}].api_token must be a non-empty string")

    filter_values: list[str] = []
    lang = ""
    for request in ctx.requests:
        filter_value = request.get("filter")
        if filter_value is None:
            filter_value = request.get("query")
        if not isinstance(filter_value, str) or not filter_value:
            raise ValueError("Todoist requests require 'filter' to be a non-empty string")

        request_lang = request.get("lang")
        if request_lang is not None and (not isinstance(request_lang, str) or not request_lang):
            raise ValueError("Todoist request 'lang' must be a non-empty string when provided")
        if request_lang is not None:
            lang = request_lang

        filter_values.append(filter_value)

    return api_token, filter_values, lang


class TodoistProvider:
    kind: ClassVar[str] = "todoist"

    def count(self, ctx: ProviderContext) -> int:
        api_token, filter_values, lang = _parse_todoist_input(ctx)
        return get_task_count(api_token, filter_values=filter_values, lang=lang)


class TodoistTimeBlockProvider:
    kind: ClassVar[str] = "todoist"

    def time_blocks(self, ctx: ProviderContext) -> list[TimeBlockRow]:
        api_token, filter_values, lang = _parse_todoist_input(ctx)
        return get_time_blocks(api_token, filter_values=filter_values, lang=lang)


provider_registry.register_count_provider(TodoistProvider)
provider_registry.register_timeblocks_provider(TodoistTimeBlockProvider)
