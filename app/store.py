"""Reading and writing glance's files: tasks.md (the lists) and events.log (what happened).

The only module that touches the disk. It moves text in and out; turning text into lists is
core's job (`app.core.tasks_md`).
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from app.core import tasks_md
from app.core.model import Event, Lists
from app.core.tasks_md import Problem

TASKS_FILE = "tasks.md"
EVENTS_FILE = "events.log"


@dataclass(frozen=True)
class Stamp:
    """Enough to tell whether tasks.md changed on disk since it was last read or written."""

    mtime_ns: int
    size: int


NO_FILE = Stamp(0, -1)


@dataclass(frozen=True)
class Snapshot:
    lists: Lists
    stamp: Stamp


@dataclass(frozen=True)
class Unreadable:
    path: Path
    problem: Problem

    def message(self) -> str:
        return f"{self.path.name} line {self.problem.line}: {self.problem.message}"


class Store:
    def __init__(self, folder: Path) -> None:
        self.folder = folder
        self.tasks_path = folder / TASKS_FILE
        self.events_path = folder / EVENTS_FILE

    def stamp(self) -> Stamp:
        if not self.tasks_path.exists():
            return NO_FILE
        info = self.tasks_path.stat()
        return Stamp(info.st_mtime_ns, info.st_size)

    def load(self) -> Snapshot | Unreadable:
        """The lists in tasks.md. No file yet means empty lists. Creates the data folder."""
        self.folder.mkdir(parents=True, exist_ok=True)
        stamp = self.stamp()
        if stamp == NO_FILE:
            return Snapshot(Lists(), stamp)
        text = self.tasks_path.read_text(encoding="utf-8-sig")
        match tasks_md.parse(text):
            case Problem() as problem:
                return Unreadable(self.tasks_path, problem)
            case Lists() as lists:
                return Snapshot(lists, stamp)

    def save(self, lists: Lists) -> Stamp:
        """Write tasks.md atomically: a temp file next to it, flushed to disk, then swapped in."""
        self.folder.mkdir(parents=True, exist_ok=True)
        temp = self.folder / f"{TASKS_FILE}.tmp"
        with temp.open("w", encoding="utf-8", newline="\n") as file:
            file.write(tasks_md.render(lists))
            file.flush()
            os.fsync(file.fileno())
        info = temp.stat()  # taken before the swap, so an edit right after it is still noticed
        os.replace(temp, self.tasks_path)
        return Stamp(info.st_mtime_ns, info.st_size)

    def append(self, events: Sequence[Event]) -> None:
        if not events:
            return
        self.folder.mkdir(parents=True, exist_ok=True)
        with self.events_path.open("a", encoding="utf-8", newline="\n") as file:
            file.writelines(f"{event_line(event)}\n" for event in events)


def event_line(event: Event) -> str:
    """`2026-10-17 09:58:40+01:00  parked    Do ticket 1234 · left off: retry loop`"""
    at = event.at.isoformat(sep=" ", timespec="seconds")
    title = event.title.replace(" · ", " - ")
    detail = f" · {event.detail}" if event.detail else ""
    return f"{at}  {event.kind:<8}  {title}{detail}"
