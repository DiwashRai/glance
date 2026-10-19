"""Reading and writing glance's files: tasks.md (the lists) and events.log (what happened).

The only module that touches the disk. It moves text in and out; turning text into lists is
core's job (`app.core.tasks_md`).
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from app.core import events_log, tasks_md
from app.core.events_log import History
from app.core.model import Event, Lists, Problem

TASKS_FILE = "tasks.md"
EVENTS_FILE = "events.log"
# How much of the end of events.log is read: about two months, parsed in under 10 ms. A task
# still active from before that (or a day of more than about 3000 events) loses its start.
EVENTS_TAIL = 256 * 1024


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
    message: str  # what's wrong, with the line number
    stamp: Stamp  # so a fix to the file can be noticed


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
        text = self.tasks_path.read_bytes().decode("utf-8-sig", errors="replace")
        match _not_utf8(text) if "�" in text else tasks_md.parse(text):
            case Problem(line=line, message=message):
                return Unreadable(f"{TASKS_FILE} line {line}: {message}", stamp)
            case Lists() as lists:
                return Snapshot(lists, stamp)

    def save(self, lists: Lists) -> Stamp:
        """Write tasks.md atomically: a temp file next to it, flushed to disk, then swapped in."""
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
        with self.events_path.open("a", encoding="utf-8", newline="\n") as file:
            file.writelines(f"{events_log.line(event)}\n" for event in events)

    def history(self) -> History | Problem:
        """What events.log says happened lately, oldest first: its last whole lines, so it
        stays quick however long the log gets. No file yet means nothing has happened."""
        if not self.events_path.exists():
            return History()
        data = self.events_path.read_bytes()
        cut = data.rfind(b"\n", 0, max(len(data) - EVENTS_TAIL, 0)) + 1  # 0 for a short log
        first = data.count(b"\n", 0, cut) + 1
        text = data[cut:].decode("utf-8-sig", errors="replace")
        if "�" in text:
            problem = _not_utf8(text)
            return Problem(problem.line + first - 1, problem.message)
        return events_log.parse(text, first)


def _not_utf8(text: str) -> Problem:
    """Bytes that aren't UTF-8 decode to U+FFFD; point at the first one."""
    line = text[: text.index("�")].count("\n") + 1
    return Problem(line, "this isn't UTF-8 text: save the file as UTF-8")
