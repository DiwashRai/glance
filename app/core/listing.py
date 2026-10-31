"""The lists as text, numbered the way commands count them: what `glance` prints on the command
line. Pure: lists in, text out.

```
Active
  Do ticket 1234
    [x] reproduce it
    [ ] compare node versions
Focus
  1  Fix the vulnerabilities
Parked
  1  1129 password reset flow · waiting on review
  2  Tidy logging config · left off: half done on chore/logging
  3  Bump deps · ★ today's highlight · queued
Quick
  q1  merge 1129 ~3m
Today
  1  14:00-15:30 deep work
  2  17:30-18:30 run !
```
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date

from app.core import blocks, highlight
from app.core.model import FromQuick, Idle, Lists, ParkedTask, Queued, Task, parked_note, shown
from app.core.tasks_md import BOXES

NOTHING = "  nothing"
MARKS: dict[highlight.Shine, str] = {"today": "★", "earlier": "☆", "none": ""}


def listing(lists: Lists, today: date) -> str:
    """As the overlay's cards have them, with today's blocks only: a plan for another day is
    stale."""
    sections = (
        ("Active", _active(lists.active, today)),
        ("Focus", _numbered(lists.focus)),
        ("Parked", _numbered(_parked(item, today) for item in lists.parked)),
        ("Quick", _numbered((shown(task) for task in lists.quick), "q")),
        ("Today", _numbered(blocks.text(block) for block in blocks.planned(lists.plan, today))),
    )
    lines = [line for heading, rows in sections for line in (heading, *(rows or (NOTHING,)))]
    return "\n".join(lines)


def _active(active: Task | FromQuick | Idle, today: date) -> tuple[str, ...]:
    match active:
        case FromQuick(task=task):
            return (f"  {shown(task)} · from quick",)
        case Task() as task:
            steps = (f"    [{BOXES[step.state]}] {step.text}" for step in task.steps)
            return (f"  {_joined(shown(task), _star(task, today))}", *steps)
        case Idle():
            return ()


def _parked(item: ParkedTask, today: date) -> str:
    queued = "queued" if item.reason == Queued() else ""
    return _joined(shown(item.task), _star(item.task, today), queued, parked_note(item))


def _star(task: Task, today: date) -> str:
    """`★ today's highlight`, `☆ yesterday's highlight`, or "" when it isn't starred."""
    star = highlight.said(task, today)
    return f"{MARKS[highlight.shine(task, today)]} {star}" if star else ""


def _joined(*parts: str) -> str:
    return " · ".join(part for part in parts if part)


def _numbered(rows: Iterable[str], prefix: str = "") -> tuple[str, ...]:
    return tuple(f"  {prefix}{number}  {row}" for number, row in enumerate(rows, 1))
