"""Glance's lists and what happens to them, as plain frozen types.

Bad states can't be written down: Active is a task or idle, and a parked task is either left off
(with an optional "where I left off" note) or waiting on something. Focus is one or two things
the work is for, kept in view as a reminder: never made active, only added and removed. Quick
holds small next actions, smallest first. The plan is today's blocks of set-aside time.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Literal

FOCUS_SLOTS = 2
# A rough size at the end of a title: ~3m, ~1h. On its own (`~5m`) it leaves an empty title.
SIZE = re.compile(r"(?:\A|\s+)~([1-9][0-9]{0,3})([mh])\Z")


StepState = Literal["open", "done", "skipped", "left"]  # left: skipped twice, not come back to


@dataclass(frozen=True)
class Step:
    text: str
    state: StepState = "open"


@dataclass(frozen=True)
class Task:
    title: str
    minutes: int = 0  # its rough size, 0 when none was given
    steps: tuple[Step, ...] = ()  # an ordered checklist, one level deep


@dataclass(frozen=True)
class OnStep:
    """On an open step: the first one."""

    index: int


@dataclass(frozen=True)
class BackTo:
    """No step is open, so back round to the first skipped one."""

    index: int


@dataclass(frozen=True)
class OnlyLeft:
    """Every step is done or left (skipped twice), and at least one is left."""


@dataclass(frozen=True)
class AllDone:
    """Every step is done."""


@dataclass(frozen=True)
class NoSteps:
    pass


Where = OnStep | BackTo | OnlyLeft | AllDone | NoSteps


def where(task: Task) -> Where:
    """Where the task is up to in its steps."""
    states = [step.state for step in task.steps]
    if "open" in states:
        return OnStep(states.index("open"))
    if "skipped" in states:
        return BackTo(states.index("skipped"))
    if "left" in states:
        return OnlyLeft()
    return AllDone() if states else NoSteps()


def step_line(task: Task) -> str:
    """Where the task is up to, as the Active card and Parked show it: "rerun CI · 2/4",
    "back to skipped: rerun CI", "only skipped steps left", "all 4 steps done". "" with no
    steps."""
    count = len(task.steps)
    match where(task):
        case OnStep(index=index):
            return f"{task.steps[index].text} · {index + 1}/{count}"
        case BackTo(index=index):
            return f"back to skipped: {task.steps[index].text}"
        case OnlyLeft():
            return "only skipped steps left"
        case AllDone():
            return f"all {count} steps done" if count > 1 else "the step is done"
        case NoSteps():
            return ""


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


def parked_note(parked: ParkedTask) -> str:
    """The line under a parked task: what it's waiting on, where I left off, or else where it's
    up to in its steps. "" when there's none."""
    match parked.reason:
        case Waiting(on=on):
            return f"waiting on {on}"
        case LeftOff(note=""):
            return step_line(parked.task)
        case LeftOff(note=note):
            return f"left off: {note}"


@dataclass(frozen=True)
class Block:
    """Time set aside on the plan's day: `14:00-15:30 deep work`. It ends by midnight."""

    start: time
    end: time
    what: str
    must: bool = False  # it must happen today: a newer block never cuts it


@dataclass(frozen=True)
class Plan:
    day: date  # a plan for another day is stale: it's kept, but not shown or added to
    blocks: tuple[Block, ...] = ()  # by start time, never overlapping


@dataclass(frozen=True)
class NoPlan:
    """No blocks have been planned yet."""


@dataclass(frozen=True)
class Lists:
    active: Task | FromQuick | Idle = Idle()
    parked: tuple[ParkedTask, ...] = ()  # most recently touched first
    focus: tuple[str, ...] = ()  # at most FOCUS_SLOTS, oldest first
    quick: tuple[Task, ...] = ()  # smallest first
    plan: Plan | NoPlan = NoPlan()


EventKind = Literal[
    "started",
    "parked",
    "waiting",
    "resumed",
    "finished",
    "crossed",  # a Quick item ticked off without starting it
    "removed",  # a Parked or Quick item taken off its card, not done
    "focused",
    "unfocused",
    "added",
    "ticked",
    "skipped",
    "planned",  # a block added to today's plan
    "unplanned",
]


@dataclass(frozen=True)
class Event:
    at: datetime
    kind: EventKind
    title: str
    detail: str = ""


@dataclass(frozen=True)
class Problem:
    """Why tasks.md or events.log can't be read: the line, and what's wrong with it."""

    line: int
    message: str


@dataclass(frozen=True)
class Message:
    """One for me in the inbox, from an agent or a script (`glance --from chief '...'`), until I
    clear it."""

    sender: str
    at: str  # when it came: 12:41
    text: str
    key: str  # which one it is in the inbox, so clearing it clears that one


@dataclass(frozen=True)
class HudSettings:
    """How the HUD on the taskbar looks. Its theme is picked from the tray menu."""

    labels: Literal["icons", "text"] = "icons"


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
    step: tuple[str, ...] = ("step",)
    skip: tuple[str, ...] = ("skip", ">")
    finish: tuple[str, ...] = ("finish",)
    unblock: tuple[str, ...] = ("unblock",)
    remove: tuple[str, ...] = ("rm",)
    # Not command words: the agents a line starting with one space goes to, then two or more
    agents: tuple[str, ...] = ("assistant", "chief")
