"""Turning tasks.md text into lists and back. Pure: text in, values out.

```
# Active
- Do ticket 1234

# Focus
- Fix the vulnerabilities

# Parked
- 1129 password reset flow
  waiting on: review
- Tidy logging config
  left off: half done on chore/logging
```

A file that doesn't fit is refused whole, with the line number, rather than guessed at.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.model import FOCUS_SLOTS, Idle, LeftOff, Lists, ParkedTask, Task, Waiting

HEADINGS = {"# Active": "active", "# Focus": "focus", "# Parked": "parked"}
WAITING_ON = "waiting on:"
LEFT_OFF = "left off:"


@dataclass(frozen=True)
class Problem:
    line: int
    message: str


def render(lists: Lists) -> str:
    lines = ["# Active"]
    match lists.active:
        case Task(title=title):
            lines.append(f"- {title}")
        case Idle():
            pass
    lines += ["", "# Focus", *(f"- {text}" for text in lists.focus), "", "# Parked"]
    for parked in lists.parked:
        lines.append(f"- {parked.task.title}")
        lines += _note_lines(parked.reason)
    return "\n".join(lines) + "\n"


def _note_lines(reason: LeftOff | Waiting) -> list[str]:
    match reason:
        case Waiting(on=on):
            return [f"  {WAITING_ON} {on}"]
        case LeftOff(note=""):
            return []
        case LeftOff(note=note):
            return [f"  {LEFT_OFF} {note}"]


def parse(text: str) -> Lists | Problem:
    """Lines are split on newlines only (a stray `\\r` is trimmed), so odd characters in a title
    stay in the title rather than splitting it."""
    reader = _Reader()
    for number, line in enumerate(text.split("\n"), start=1):
        problem = reader.feed(line.rstrip())
        if problem:
            return Problem(number, problem)
    return reader.lists()


class _Reader:
    """Reads one line at a time. `feed` returns what's wrong with the line, or "" if it's fine."""

    def __init__(self) -> None:
        self.section = ""
        self.seen: set[str] = set()
        self.active: list[Task] = []
        self.parked: list[ParkedTask] = []
        self.focus: list[str] = []
        self.noted = False

    def lists(self) -> Lists:
        active = self.active[0] if self.active else Idle()
        return Lists(active, tuple(self.parked), tuple(self.focus))

    def feed(self, line: str) -> str:
        if not line:
            return ""
        if line.startswith("#"):
            return self._heading(line)
        if not self.section:
            return "text before the first heading"
        if line == "-" or line.startswith("- "):
            return self._task(line[1:].strip())
        if line.startswith("  "):
            return self._note(line.strip())
        return "glance can't read this line"

    def _heading(self, line: str) -> str:
        section = HEADINGS.get(line, "")
        if not section:
            return f"unknown heading '{line}'"
        if section in self.seen:
            return f"'{line}' appears twice"
        self.seen.add(section)
        self.section = section
        return ""

    def _task(self, title: str) -> str:
        if not title:
            return "a task needs a title"
        if self.section == "parked":
            self.parked.append(ParkedTask(Task(title), LeftOff()))
            self.noted = False
            return ""
        if self.section == "focus":
            return self._focus(title)
        if self.active:
            return "only one task can be active"
        self.active.append(Task(title))
        return ""

    def _focus(self, text: str) -> str:
        if len(self.focus) >= FOCUS_SLOTS:
            return f"focus holds at most {FOCUS_SLOTS}"
        self.focus.append(text)
        return ""

    def _note(self, text: str) -> str:
        if text.startswith("- "):
            return "steps aren't supported yet"
        if self.section == "active":
            return "the active task can't have a note"
        if self.section == "focus":
            return "a focus can't have a note"
        if not self.parked or self.noted:
            return "a note goes on its own line under a parked task, one per task"
        match _reason(text):
            case _BadNote(message=message):
                return message
            case LeftOff() | Waiting() as reason:
                self.parked[-1] = ParkedTask(self.parked[-1].task, reason)
                self.noted = True
                return ""


@dataclass(frozen=True)
class _BadNote:
    message: str


def _reason(text: str) -> LeftOff | Waiting | _BadNote:
    lowered = text.lower()
    if lowered.startswith(WAITING_ON):
        on = text[len(WAITING_ON) :].strip()
        return Waiting(on) if on else _BadNote("waiting on what?")
    if lowered.startswith(LEFT_OFF):
        return LeftOff(text[len(LEFT_OFF) :].strip())
    return _BadNote(f"a note starts with '{WAITING_ON}' or '{LEFT_OFF}'")
