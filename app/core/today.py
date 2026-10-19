"""Today: what I was on, and when, worked out from the history, beside the planned blocks. Pure,
with the time passed in.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from itertools import pairwise

from app.core.events_log import History, as_written
from app.core.model import Block, Event, EventKind, FromQuick, Idle, Problem, Task, working

STARTS: tuple[EventKind, ...] = ("started", "resumed")
STOPS: tuple[EventKind, ...] = ("parked", "waiting", "finished")  # not "crossed": see worked

Log = History | Problem  # events.log as read: what happened, or why it can't be read
NOTHING_YET: Log = History()


@dataclass(frozen=True)
class Span:
    """Time on one active task, from when it started or was resumed to when it stopped."""

    title: str
    start: datetime
    end: datetime
    going: bool = False  # still on it, so it ends now


@dataclass(frozen=True)
class Slot:
    """A block from today's plan, on the clock."""

    number: int  # as unblock counts it
    block: Block
    start: datetime
    end: datetime


@dataclass(frozen=True)
class Day:
    now: datetime
    since: datetime  # the start of today, where the time on tasks is counted from
    spans: tuple[Span, ...] = ()  # oldest first
    slots: tuple[Slot, ...] = ()  # by start time
    problem: str = ""  # why events.log can't be read


def day(
    history: Log,
    now: datetime,
    since: datetime,
    active: Task | FromQuick | Idle,
    slots: tuple[Slot, ...],
) -> Day:
    """The plan shows even when events.log can't be read."""
    match history:
        case History(events=events):
            return Day(now, since, worked(events, now, _title(active)), slots)
        case Problem(line=line, message=message):
            return Day(now, since, slots=slots, problem=f"events.log line {line}: {message}")


def logged(history: Log, events: Sequence[Event]) -> Log:
    """The history with a command's events added, as they'll read back once written."""
    match history:
        case History(events=before):
            return History((*before, *(replace(e, title=as_written(e.title)) for e in events)))
        case Problem() as problem:
            return problem


def worked(events: Sequence[Event], now: datetime, active: str) -> tuple[Span, ...]:
    """Each start runs until the next start or stop. Ticking off a Quick item (`crossed`) is
    neither: Active carries on. The last start, if nothing stopped it, is still going only while
    it's the active task (`active`, its title as written, or "" when nothing is): if tasks.md
    was edited by hand, when it stopped isn't known, so it's left out.
    """
    moves = [event for event in events if event.kind in STARTS or event.kind in STOPS]
    spans = [Span(a.title, a.at, b.at) for a, b in pairwise(moves) if a.kind in STARTS]
    on = [a for a in moves[-1:] if a.kind in STARTS and a.title == active]
    spans += [Span(a.title, a.at, now, going=True) for a in on]
    return tuple(span for span in spans if span.end >= span.start)  # not from a clock set back


def _title(active: Task | FromQuick | Idle) -> str:
    match working(active):
        case Task(title=title):
            return as_written(title)
        case Idle():
            return ""


def total(spans: Sequence[Span], since: datetime) -> timedelta:
    """Time on tasks from `since`, counting only the part of a span after it."""
    after = (span.end - max(span.start, since) for span in spans if span.end > since)
    return sum(after, timedelta())


def duration_text(time: timedelta) -> str:
    """`45m`, `2h 10m`, `3h`."""
    hours, minutes = divmod(int(time.total_seconds()) // 60, 60)
    if not hours:
        return f"{minutes}m"
    return f"{hours}h {minutes}m" if minutes else f"{hours}h"
