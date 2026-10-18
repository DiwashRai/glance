"""Runs what I type against the lists on disk. Plain Python, no Qt, so it's tested like core.

The window calls `open()` each time it's shown, `preview()` as I type, `run()` on Enter, and draws
the `View` it gets back. A change is saved to tasks.md first and only then kept in memory, so
what's shown never gets ahead of what's saved. The window writes the history (`write_history()`)
after drawing, so a failed history write can't leave the window showing stale lists.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, time

from app.core import blocks, today
from app.core.commands import (
    Applied,
    Ask,
    Command,
    Preview,
    Rejected,
    apply,
    parse_command,
    preview,
)
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
        self.previewed = ("", Preview())  # the line last previewed, and what it showed

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
        match parse_command(text, self.words):
            case Ask():  # for the assistant, which isn't built yet: it's cleared, and that's all
                return View(self.lists, problem=self.problem, accepted=True)
            case _ if not text.strip():
                return View(self.lists, problem=self.problem)
            case command:
                return self._apply(text, command)

    def _apply(self, text: str, command: Command) -> View:
        if self.store.stamp() != self.stamp:
            view = self.open()
            return View(view.lists, "tasks.md changed, run it again", view.problem)
        if self.problem:
            return View(self.lists, problem=self.problem)
        now = self.now()
        if self._moved_on(text, now):
            said = f"it's {now:%H:%M} now, which changes what that does: check, then run it again"
            return View(self.lists, said)
        match apply(self.lists, command, now):
            case Rejected(reason=reason):
                return View(self.lists, reason)
            case Applied(lists=lists, events=events, message=message):
                self.stamp = self.store.save(lists)
                self.lists = lists
                self.history = events
                self.log = today.logged(self.log, events)
                return View(lists, message, accepted=True)

    def preview(self, text: str) -> Preview:
        """What the line being typed will do, worked out on each key press."""
        self.previewed = (text, preview(text, self.words, self.lists, self.now()))
        return self.previewed[1]

    def _moved_on(self, text: str, now: datetime) -> bool:
        """Whether what was shown for this line has changed with the clock alone: at 08:59, `9`
        is 09:00, but at 09:01 it's 21:00, which may cut a different block. The preview's plan
        is compared too, as the note doesn't show times."""
        shown_for, shown = self.previewed
        return shown_for == text and preview(text, self.words, self.lists, now) != shown

    def day(self) -> today.Day:
        """What I've been on today, up to now. If writing the history fails, this shows the
        last change until the next open re-reads events.log."""
        now = self.now()
        planned = enumerate(blocks.planned(self.lists.plan, now.date()), start=1)
        slots = tuple(
            today.Slot(number, block, _at(now, block.start), _at(now, block.end))
            for number, block in planned
            if _exists(now, block.start) and _exists(now, block.end)
        )
        return today.day(self.log, now, _at(now, time()), self.lists.active, slots)

    def write_history(self) -> None:
        """Append the last change's events to events.log."""
        events, self.history = self.history, ()
        self.store.append(events)


def _exists(now: datetime, clock: time) -> bool:
    """False for a time in the hour the clocks skip, the night they go forward. A block that
    starts or ends then is left off the card that night; it keeps its number for unblock."""
    wall = datetime.combine(now.date(), clock)
    return _at(now, clock).replace(tzinfo=None) == wall


def _at(now: datetime, clock: time) -> datetime:
    """That time on now's day, with the UTC offset it has then, which isn't now's on the day the
    clocks change. That takes the zone's rules, so it's worked out here, not in core."""
    return datetime.combine(now.date(), clock).astimezone()
