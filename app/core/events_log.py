"""Turning events and events.log lines into each other. Pure: text in, values out.

```
2026-10-17 09:58:40+01:00  parked     Do ticket 1234 · left off: retry loop
```

A line that doesn't fit refuses the whole log, with the line number, as tasks.md does.
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import datetime
from typing import get_args

from app.core.model import Event, EventKind
from app.core.tasks_md import Problem

LINE = re.compile(r"(\S+ \S+) +(\S+) +(.+)")
STAMP = re.compile(
    r"([1-9]\d{3})-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01]) "
    r"([01]\d|2[0-3]):[0-5]\d:[0-5]\d[+-]([01]\d|2[0-3]):[0-5]\d",
    re.ASCII,  # `fromisoformat` takes only 0-9, not every digit Unicode has
)
KINDS: dict[str, EventKind] = {kind: kind for kind in get_args(EventKind)}
DETAIL = " · "


@dataclass(frozen=True)
class History:
    events: tuple[Event, ...] = ()  # oldest first


def as_written(title: str) -> str:
    """A title as its line reads back: with no `·` in it, the detail's ` · ` is the first one."""
    return title.replace("·", "-")


def line(event: Event) -> str:
    """`2026-10-17 09:58:40+01:00  parked     Do ticket 1234 · left off: retry loop`"""
    at = event.at.isoformat(sep=" ", timespec="seconds")
    detail = f"{DETAIL}{event.detail}" if event.detail else ""
    return f"{at}  {event.kind:<9}  {as_written(event.title)}{detail}"


def parse(text: str, first: int = 1) -> History | Problem:
    """`first` is the file's line number for the text's first line, when it's only the end of
    the file. Blank lines are skipped. The kind's column got wider once, so any run of spaces
    splits. Only a newline ends a line: a title may hold other line breaks, as tasks.md allows."""
    events: list[Event] = []
    for number, written_line in enumerate(text.split("\n"), start=first):
        if not written_line.strip():
            continue
        match _event(written_line.strip()):
            case Event() as event:
                events.append(event)
            case Problem(message=message):
                return Problem(number, message)
    return History(tuple(events))


def _event(written_line: str) -> Event | Problem:
    found = LINE.fullmatch(written_line)
    if not found:
        return Problem(0, "a line is a time, what happened, then the task")
    at, kind, rest = found.groups()
    if not _real(at):
        return Problem(0, f"{at!r} isn't a real time, like 2026-10-17 09:58:40+01:00")
    if kind not in KINDS:
        return Problem(0, f"{kind!r} isn't something glance logs")
    title, _, detail = rest.partition(DETAIL)
    # An older glance kept a `·` that wasn't between spaces
    return Event(datetime.fromisoformat(at), KINDS[kind], as_written(title), detail)


def _real(at: str) -> bool:
    """Checked here, so `fromisoformat` can't fail on, say, 30 February."""
    found = STAMP.fullmatch(at)
    if not found:
        return False
    year, month, day = int(found[1]), int(found[2]), int(found[3])
    return day <= calendar.monthrange(year, month)[1]
