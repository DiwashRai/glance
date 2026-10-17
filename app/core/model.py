"""Glance's lists and what happens to them, as plain frozen types.

Bad states can't be written down: Active is a task or idle, and a parked task is either left off
(with an optional "where I left off" note) or waiting on something. Focus is one or two things
the work is for, kept in view as a reminder: never made active, only added and removed. Quick
holds small next actions, smallest first.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

FOCUS_SLOTS = 2
# A rough size at the end of a title: ~3m, ~1h. On its own (`~5m`) it leaves an empty title.
SIZE = re.compile(r"(?:\A|\s+)~([1-9][0-9]{0,3})([mh])\Z")


@dataclass(frozen=True)
class Task:
    title: str
    minutes: int = 0  # its rough size, 0 when none was given


@dataclass(frozen=True)
class FromQuick:
    """The active task, taken from Quick: put away with no note, it goes back there."""

    task: Task


def sized(text: str) -> Task:
    """A task from its text, taking a size like `~3m` or `~1h` off the end if there is one."""
    match SIZE.split(text, maxsplit=1):
        case [title, number, unit, ""]:
            return Task(title, int(number) * (60 if unit == "h" else 1))
        case _:
            return Task(text)


def shown(task: Task) -> str:
    """The title with its size, as it's written in tasks.md and shown."""
    return " ".join(part for part in (task.title, size_text(task)) if part)


def working(active: Task | FromQuick | Idle) -> Task | Idle:
    """The active task, wherever it came from."""
    match active:
        case FromQuick(task=task):
            return task
        case Task() | Idle():
            return active


def size_text(task: Task) -> str:
    """`~3m`, `~1h` or `~90m`; "" when it has no size."""
    if not task.minutes:
        return ""
    if task.minutes % 60:
        return f"~{task.minutes}m"
    return f"~{task.minutes // 60}h"


def smallest_first(tasks: tuple[Task, ...]) -> tuple[Task, ...]:
    """Unsized last; the same size keeps its order."""
    return tuple(sorted(tasks, key=lambda task: (not task.minutes, task.minutes)))


@dataclass(frozen=True)
class Idle:
    """Nothing is active."""


@dataclass(frozen=True)
class LeftOff:
    note: str = ""


@dataclass(frozen=True)
class Waiting:
    on: str


@dataclass(frozen=True)
class ParkedTask:
    task: Task
    reason: LeftOff | Waiting


@dataclass(frozen=True)
class Lists:
    active: Task | FromQuick | Idle = Idle()
    parked: tuple[ParkedTask, ...] = ()  # most recently touched first
    focus: tuple[str, ...] = ()  # at most FOCUS_SLOTS, oldest first
    quick: tuple[Task, ...] = ()  # smallest first


EventKind = Literal[
    "started", "parked", "waiting", "resumed", "finished", "focused", "unfocused", "added"
]


@dataclass(frozen=True)
class Event:
    at: datetime
    kind: EventKind
    title: str
    detail: str = ""


@dataclass(frozen=True)
class HudSettings:
    """How the HUD on the taskbar looks."""

    look: Literal["native", "box"] = "native"  # native: drawn straight onto the taskbar
    labels: Literal["icons", "text"] = "icons"
    show_active: bool = True


@dataclass(frozen=True)
class CommandWords:
    """The words that start each command. Lower case, one word each, no word used twice."""

    new: tuple[str, ...] = ("new", "+")
    park: tuple[str, ...] = ("park", "pause", "shelve", "defer")
    wait: tuple[str, ...] = ("wait",)
    switch: tuple[str, ...] = ("switch", "s")
    done: tuple[str, ...] = ("done", "d")
    focus: tuple[str, ...] = ("focus",)
    unfocus: tuple[str, ...] = ("unfocus",)
    quick: tuple[str, ...] = ("quick", "q")
