"""Runs what I type against the lists on disk. Plain Python, no Qt, so it's tested like core.

The window calls `open()` each time it's shown, `run()` on Enter, and draws the `View` it gets
back. A change is saved to tasks.md first and only then kept in memory, so what's shown never
gets ahead of what's saved. The window writes the history (`write_history()`) after drawing, so
a failed history write can't leave the window showing stale lists.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, time

from app.core import today
from app.core.commands import Applied, Rejected, apply, parse_command
from app.core.model import CommandWords, Event, Lists
from app.store import NO_FILE, Snapshot, Store, Unreadable


@dataclass(frozen=True)
class View:
    """What the window shows."""

    lists: Lists
    message: str = ""
    problem: str = ""  # why tasks.md can't be read; commands are refused until it's fixed
    accepted: bool = False  # the command ran, so the text box can be cleared


class Controller:
    def __init__(self, store: Store, words: CommandWords, now: Callable[[], datetime]) -> None:
        self.store = store
        self.words = words
        self.now = now
        self.lists = Lists()
        self.stamp = NO_FILE
        self.problem = ""
        self.history: tuple[Event, ...] = ()  # the last change's, until they're written
        self.log: today.Log = today.NOTHING_YET  # events.log as last read, plus what's since

    def open(self) -> View:
        """Read tasks.md and events.log again: either may have changed since the window was
        last shown."""
        self.log = self.store.history()
        match self.store.load():
            case Snapshot(lists=lists, stamp=stamp):
                self.lists, self.stamp, self.problem = lists, stamp, ""
            case Unreadable(message=message, stamp=stamp):
                self.stamp = stamp
                self.problem = f"{message}. Fix it, then run the command again."
        return View(self.lists, problem=self.problem)

    def run(self, text: str) -> View:
        if not text.strip():
            return View(self.lists, problem=self.problem)
        if self.store.stamp() != self.stamp:
            view = self.open()
            return View(view.lists, "tasks.md changed, run it again", view.problem)
        if self.problem:
            return View(self.lists, problem=self.problem)
        match apply(self.lists, parse_command(text, self.words), self.now()):
            case Rejected(reason=reason):
                return View(self.lists, reason)
            case Applied(lists=lists, events=events, message=message):
                self.stamp = self.store.save(lists)
                self.lists = lists
                self.history = events
                self.log = today.logged(self.log, events)
                return View(lists, message, accepted=True)

    def day(self) -> today.Day:
        """What I've been on today, up to now. If writing the history fails, this shows the
        last change until the next open re-reads events.log."""
        now = self.now()
        return today.day(self.log, now, _midnight(now), self.lists.active)

    def write_history(self) -> None:
        """Append the last change's events to events.log."""
        events, self.history = self.history, ()
        self.store.append(events)


def _midnight(now: datetime) -> datetime:
    """The start of now's day, with the UTC offset it had then, which isn't now's on the day
    the clocks change. That takes the zone's rules, so it's worked out here, not in core."""
    return datetime.combine(now.date(), time()).astimezone()
