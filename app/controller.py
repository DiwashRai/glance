"""Runs what I type against the lists on disk. Plain Python, no Qt, so it's tested like core.

The window calls `open()` each time it's shown, `preview()` as I type, `run()` on Enter, and draws
the `View` it gets back. `glance` on the command line does the same for one line. The HUD asks
for `saved()`. A change is saved to tasks.md first and only then kept in memory, so
what's shown never gets ahead of what's saved. The window writes the history (`write_history()`)
after drawing, so a failed history write can't leave the window showing stale lists.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime, time
from typing import Protocol

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
    # Shown in red: why tasks.md can't be read (commands are refused until it's fixed), or why a
    # line couldn't be sent to an agent
    problem: str = ""
    accepted: bool = False  # the command ran, so the text box can be cleared


class Agents(Protocol):
    """The agents a line can be sent to: herdr's, in the app. Neither call raises: each returns
    "" when all is well, else why not."""

    def check(self, name: str) -> str: ...

    def send(self, name: str, text: str) -> str: ...


class Controller:
    def __init__(
        self, store: Store, words: CommandWords, now: Callable[[], datetime], agents: Agents
    ) -> None:
        self.store = store
        self.words = words
        self.now = now
        self.agents = agents
        self.trouble: dict[str, str] = {}  # what's wrong with each agent, "" if nothing, this open
        self.lists = Lists()
        self.stamp = NO_FILE
        self.problem = ""
        self.history: tuple[Event, ...] = ()  # the last change's, until they're written
        self.log: today.Log = today.NOTHING_YET  # events.log as last read, plus what's since
        self.previewed = ("", Preview())  # the line last previewed, and what it showed
        self.seen = (NO_FILE, Lists())  # tasks.md as the HUD last read it

    def open(self) -> View:
        """Read tasks.md and events.log again: either may have changed since the window was
        last shown. Whether the agents are running is checked again too, when next needed."""
        self.log = self.store.history()
        self.trouble = {}
        match self.store.load():
            case Snapshot(lists=lists, stamp=stamp):
                self.lists, self.stamp, self.problem = lists, stamp, ""
            case Unreadable(message=message, stamp=stamp):
                self.stamp = stamp
                self.problem = f"{message}. Commands wait until it's fixed."
        return View(self.lists, problem=self.problem)

    def saved(self) -> Lists:
        """The lists as tasks.md has them, for the HUD, read again only when it changes: an agent
        may have changed them with `glance` on the command line. A file that can't be read keeps
        the last lists that could. This is apart from what a typed line runs against, so a line
        typed against what the overlay shows is still checked against the file first."""
        stamp, lists = self.seen
        if self.store.stamp() == stamp:
            return lists
        match self.store.load():
            case Snapshot(lists=read, stamp=stamp):
                self.seen = (stamp, read)
            case Unreadable(stamp=stamp):
                self.seen = (stamp, lists)
        return self.seen[1]

    def run(self, text: str) -> View:
        match parse_command(text, self.words):
            case Ask(agent=agent, text=asked):
                return self._ask(agent, asked)
            case _ if not text.strip():
                return View(self.lists, problem=self.problem)
            case command:
                return self._apply(text, command)

    def _ask(self, agent: str, text: str) -> View:
        """Typed into the agent's pane. Only spaces send nothing, but clear the line like a sent
        one. If it can't be sent, the line stays, to send again."""
        if not text:
            return View(self.lists, problem=self.problem, accepted=True)
        why = self.agents.send(agent, text)
        self.trouble[agent] = why
        if why:
            return View(self.lists, problem=why)
        return View(self.lists, f"sent to {agent}", self.problem, accepted=True)

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
        """What the line being typed will do, worked out on each key press. For an agent, the note
        names it, or says what's wrong; herdr is only asked once per open."""
        shown = preview(text, self.words, self.lists, self.now())
        if shown.agent:
            why = self._trouble(shown.agent)
            shown = replace(shown, note=why or shown.agent, trouble=bool(why))
        self.previewed = (text, shown)
        return shown

    def _trouble(self, agent: str) -> str:
        if agent not in self.trouble:
            self.trouble[agent] = self.agents.check(agent)
        return self.trouble[agent]

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
