"""Glance's lists and what happens to them, as plain frozen types.

Bad states can't be written down: Active is a task or idle, and a parked task is either left off
(with an optional "where I left off" note) or waiting on something. Focus is one or two things
the work is for, kept in view as a reminder: never made active, only added and removed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

FOCUS_SLOTS = 2


@dataclass(frozen=True)
class Task:
    title: str


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
    active: Task | Idle = Idle()
    parked: tuple[ParkedTask, ...] = ()  # most recently touched first
    focus: tuple[str, ...] = ()  # at most FOCUS_SLOTS, oldest first


EventKind = Literal["started", "parked", "waiting", "resumed", "finished", "focused", "unfocused"]


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
