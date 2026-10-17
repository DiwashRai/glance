"""A typed line into a command, and a command applied to the lists.

`apply` never fails: it returns the new lists with the events and a message, or a rejection that
says why and changes nothing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from app.core.model import CommandWords, Event, Idle, LeftOff, Lists, ParkedTask, Task, Waiting


@dataclass(frozen=True)
class New:
    title: str


@dataclass(frozen=True)
class Park:
    note: str


@dataclass(frozen=True)
class Wait:
    on: str


@dataclass(frozen=True)
class Switch:
    query: str


@dataclass(frozen=True)
class Done:
    extra: str = ""


@dataclass(frozen=True)
class Unknown:
    word: str


Command = New | Park | Wait | Switch | Done | Unknown


@dataclass(frozen=True)
class Applied:
    lists: Lists
    events: tuple[Event, ...]
    message: str


@dataclass(frozen=True)
class Rejected:
    reason: str


def parse_command(text: str, words: CommandWords) -> Command:
    """The first word decides, case-insensitively. The rest is the argument.

    Any run of whitespace in the argument, line breaks included, becomes one space, so a title or
    note is always a single line and `tasks.md` can always be read back.
    """
    first, *rest = text.split(maxsplit=1) or [""]
    word = first.lower()
    argument = " ".join(rest[0].split()) if rest else ""
    if word in words.new:
        return New(argument)
    if word in words.park:
        return Park(argument)
    if word in words.wait:
        return Wait(argument)
    if word in words.switch:
        return Switch(argument)
    if word in words.done:
        return Done(argument)
    return Unknown(first)


def apply(lists: Lists, command: Command, now: datetime) -> Applied | Rejected:
    match command:
        case New(title=title):
            return _new(lists, title, now)
        case Park(note=note):
            return _park(lists, LeftOff(note), now)
        case Wait(on=""):
            return Rejected("wait on what?")
        case Wait(on=on):
            return _park(lists, Waiting(on), now)
        case Switch(query=query):
            return _switch(lists, query, now)
        case Done(extra=""):
            return _done(lists, now)
        case Done():
            return Rejected("done finishes the active task: type just done")
        case Unknown(word=""):
            return Rejected("type a command")
        case Unknown(word=word):
            return Rejected(f"not a command: {word}")


def _set_aside(
    lists: Lists, reason: LeftOff | Waiting, now: datetime
) -> tuple[tuple[ParkedTask, ...], tuple[Event, ...]]:
    """The parked list with the active task (if any) put on top, and the event for it."""
    match lists.active:
        case Task() as task:
            return (ParkedTask(task, reason), *lists.parked), (_parked_event(task, reason, now),)
        case Idle():
            return lists.parked, ()


def _parked_event(task: Task, reason: LeftOff | Waiting, now: datetime) -> Event:
    match reason:
        case Waiting(on=on):
            return Event(now, "waiting", task.title, f"on {on}")
        case LeftOff(note=""):
            return Event(now, "parked", task.title)
        case LeftOff(note=note):
            return Event(now, "parked", task.title, f"left off: {note}")


def _also_parked(active: Task | Idle) -> str:
    match active:
        case Task(title=title):
            return f" · parked {title}"
        case Idle():
            return ""


def _new(lists: Lists, title: str, now: datetime) -> Applied | Rejected:
    if not title:
        return Rejected("new needs a title")
    parked, events = _set_aside(lists, LeftOff(), now)
    message = f"started {title}{_also_parked(lists.active)}"
    return Applied(Lists(Task(title), parked), (*events, Event(now, "started", title)), message)


def _park(lists: Lists, reason: LeftOff | Waiting, now: datetime) -> Applied | Rejected:
    match lists.active:
        case Idle():
            return Rejected("nothing is active")
        case Task(title=title):
            parked, events = _set_aside(lists, reason, now)
            return Applied(Lists(Idle(), parked), events, _parked_message(title, reason))


def _parked_message(title: str, reason: LeftOff | Waiting) -> str:
    match reason:
        case Waiting(on=on):
            return f"{title} is waiting on {on}"
        case LeftOff():
            return f"parked {title}"


def _done(lists: Lists, now: datetime) -> Applied | Rejected:
    match lists.active:
        case Task(title=title):
            finished = Event(now, "finished", title)
            return Applied(Lists(Idle(), lists.parked), (finished,), f"finished {title}")
        case Idle():
            return Rejected("nothing is active")


@dataclass(frozen=True)
class _Picked:
    index: int


def _is_number(query: str) -> bool:
    """Plain digits only (not ² or other Unicode digits), short enough to be a list position."""
    return bool(re.fullmatch(r"[0-9]{1,6}", query))


def _matches(query: str, title: str) -> bool:
    """Text matches anywhere in a title. A number only matches a whole word: 1129, not 2."""
    if _is_number(query):
        return query in re.findall(r"\w+", title)
    return query.lower() in title.lower()


def _pick(parked: tuple[ParkedTask, ...], query: str) -> _Picked | Rejected:
    """A title match first. A bare number is a position only if no title has it as a word."""
    hits = [i for i, item in enumerate(parked) if _matches(query, item.task.title)]
    if len(hits) == 1:
        return _Picked(hits[0])
    if hits:
        options = ", ".join(f"{i + 1} {parked[i].task.title}" for i in hits)
        return Rejected(f"'{query}' matches {len(hits)}: {options}")
    if _is_number(query) and 1 <= int(query) <= len(parked):
        return _Picked(int(query) - 1)
    return Rejected(f"no parked task matches '{query}'")


def _switch(lists: Lists, query: str, now: datetime) -> Applied | Rejected:
    if not query:
        return Rejected("switch to what?")
    match _pick(lists.parked, query):
        case Rejected() as rejected:
            return rejected
        case _Picked(index=index):
            chosen = lists.parked[index]
            rest = (*lists.parked[:index], *lists.parked[index + 1 :])
            parked, events = _set_aside(Lists(lists.active, rest), LeftOff(), now)
            title = chosen.task.title
            message = f"switched to {title}{_also_parked(lists.active)}{_reminder(chosen)}"
            events = (*events, Event(now, "resumed", title))
            return Applied(Lists(chosen.task, parked), events, message)


def _reminder(chosen: ParkedTask) -> str:
    """What the task was parked with, so switching back to it says where I was."""
    match chosen.reason:
        case Waiting(on=on):
            return f" · was waiting on {on}"
        case LeftOff(note=""):
            return ""
        case LeftOff(note=note):
            return f" · left off: {note}"
