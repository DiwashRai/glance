"""Today's highlight: the one task that would make the day a success, starred. Pure: the day is
passed in.

`new fix the build *` stars a new task, `star p3` a queued one, `star` alone the active one and
`unstar` takes the star off. One task has it at a time, so starring another moves it. From
midnight it's an earlier day's: still shown, hollow, until it's starred again, another task is,
or it's done.
"""

from __future__ import annotations

import re
from dataclasses import replace
from datetime import date, timedelta
from typing import Literal

from app.core.model import (
    FromQuick,
    Idle,
    Lists,
    NoStar,
    ParkedTask,
    Star,
    Task,
    parked_note,
    working,
)

MARK = "*"  # on its own at the end of a new task's line
WORD = re.compile(r"\S+")
NOT_QUICK = "a quick item can't be the highlight: it's meant to be small"

Shine = Literal["today", "earlier", "none"]  # a filled star, a hollow one, or none


def marked(text: str) -> tuple[str, bool]:
    """The text without a lone `*` at its end, and whether it had one. `ship it*` keeps its `*`,
    as a block's name keeps a `!` that isn't a word of its own."""
    words = text.split()
    if words[-1:] == [MARK]:
        return " ".join(words[:-1]), True
    return text, False


def mark_span(text: str) -> tuple[tuple[int, int], ...]:
    """Where that `*` is, as (start, end), so it's coloured as it's typed."""
    last = tuple(WORD.finditer(text))[-1:]
    return tuple(word.span() for word in last if word[0] == MARK)


def starred(lists: Lists) -> tuple[Task, ...]:
    """The task with the star, if one has it: Active first, then the queue."""
    active = tuple(task for task in held(lists.active) if task.star != NoStar())
    return (*active, *(item.task for item in lists.parked if item.task.star != NoStar()))


def cleared(lists: Lists) -> Lists:
    """The lists with no star on any task."""
    parked = tuple(replace(item, task=_unstarred(item.task)) for item in lists.parked)
    match lists.active:
        case Task() as task:
            return replace(lists, active=_unstarred(task), parked=parked)
        case FromQuick() | Idle():
            return replace(lists, parked=parked)


def held(active: Task | FromQuick | Idle) -> tuple[Task, ...]:
    """The active task, wherever it came from, or none."""
    match working(active):
        case Task() as task:
            return (task,)
        case Idle():
            return ()


def _unstarred(task: Task) -> Task:
    return replace(task, star=NoStar())


def shine(task: Task, today: date) -> Shine:
    match task.star:
        case Star(day=day) if day == today:
            return "today"
        case Star():
            return "earlier"
        case NoStar():
            return "none"


def said(task: Task, today: date) -> str:
    """`today's highlight`, `yesterday's highlight` or `the highlight from 28 Oct`; "" when it
    isn't starred."""
    match task.star:
        case Star(day=day) if day == today:
            return "today's highlight"
        case Star(day=day) if day == today - timedelta(days=1):
            return "yesterday's highlight"
        case Star(day=day):
            return f"the highlight from {day.day} {day:%b}"
        case NoStar():
            return ""


def note(parked: ParkedTask, today: date) -> str:
    """The line under a queued task. An earlier day's highlight with no other note says so."""
    earlier = shine(parked.task, today) == "earlier"
    return parked_note(parked) or (said(parked.task, today) if earlier else "")
