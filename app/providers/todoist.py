"""Todoist tasks: each request is a filter (`today | overdue`), and a task found by more than one
counts once."""

import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Sequence

import msgspec

from app.types import NonEmpty, Table

TODOIST_FILTER_URL = "https://api.todoist.com/api/v1/tasks/filter"
DEFAULT_PAGE_SIZE = 200
MAX_PAGES = 10
MAX_RETRIES = 5
logger = logging.getLogger(__name__)


class _Config(msgspec.Struct):
    api_token: NonEmpty


class _Request(msgspec.Struct):
    filter: str = ""
    query: str = ""  # an older name for `filter`
    lang: str = ""  # the filter's language, when it isn't English


class _Task(msgspec.Struct):
    id: str


class _Page(msgspec.Struct):
    results: tuple[_Task, ...]
    next_cursor: str | None = None  # none on the last page


def count(provider: Table, requests: Sequence[Table]) -> int:
    token = msgspec.convert(provider, _Config).api_token
    asked = [msgspec.convert(request, _Request) for request in requests]
    if not all(request.filter or request.query for request in asked):
        raise ValueError("a Todoist request needs a filter")
    return len({task for request in asked for task in _task_ids(token, request)})


def _task_ids(token: str, request: _Request) -> set[str]:
    query = request.filter or request.query
    found: set[str] = set()
    cursor = ""
    for _ in range(MAX_PAGES):
        answer = _load_page(_page_request(token, query, request.lang, cursor))
        page = msgspec.json.decode(answer, type=_Page)
        found.update(task.id for task in page.results)
        if not page.next_cursor:
            break
        cursor = page.next_cursor
    return found


def _page_request(
    api_token: str, filter_value: str, lang: str, cursor: str
) -> urllib.request.Request:
    params: dict[str, str | int] = {
        "query": filter_value,
        "limit": DEFAULT_PAGE_SIZE,
    }
    if lang:
        params["lang"] = lang
    if cursor:
        params["cursor"] = cursor

    url = f"{TODOIST_FILTER_URL}?{urllib.parse.urlencode(params)}"
    return urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {api_token}"},
        method="GET",
    )


def _retry_or_raise(exc: urllib.error.HTTPError, attempt: int) -> None:
    if exc.code in (502, 503) and attempt < MAX_RETRIES:
        delay = min(2**attempt, 8)
        logger.warning(
            f"Todoist request failed with HTTP {exc.code}: {exc.reason}. "
            f"Retrying in {delay}s (attempt {attempt + 2}/{MAX_RETRIES + 1})"
        )
        time.sleep(delay)
        return
    detail = exc.read().decode("utf-8", errors="replace").strip()
    raise RuntimeError(
        f"Todoist request failed with HTTP {exc.code}: {detail or exc.reason}"
    ) from exc


def _load_page(request: urllib.request.Request) -> bytes:
    for attempt in range(MAX_RETRIES + 1):
        try:
            with urllib.request.urlopen(request) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            _retry_or_raise(exc, attempt)
    raise RuntimeError("Todoist request failed after retries")
