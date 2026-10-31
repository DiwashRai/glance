"""Turning tasks.md text into lists and back. Pure: text in, values out.

```
# Active
- Do ticket 1234
  - [x] reproduce it
  - [ ] compare node versions

# Focus
- Fix the vulnerabilities

# Parked
- 1129 password reset flow
  waiting on: review
- Tidy logging config
  left off: half done on chore/logging
- Bump deps
  queued

# Quick
- merge 1129 ~3m
- reply to Sam

# Today 2026-10-18
- 14:00-15:30 deep work
- 17:30-18:30 run !
```

A file that doesn't fit is refused whole, with the line number, rather than guessed at.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace

from app.core import blocks
from app.core.model import (
    FOCUS_SLOTS,
    Block,
    FromQuick,
    Idle,
    LeftOff,
    Lists,
    NoPlan,
    ParkedTask,
    Plan,
    Problem,
    Queued,
    Step,
    StepState,
    Task,
    Waiting,
    shown,
    sized,
    smallest_first,
)

HEADINGS = {"# Active": "active", "# Focus": "focus", "# Parked": "parked", "# Quick": "quick"}
TODAY = "# Today"  # with its date: # Today 2026-10-18
WAITING_ON = "waiting on:"
LEFT_OFF = "left off:"
QUEUED = "queued"  # under a task added with new and never started
HOME_QUICK = "home: quick"  # under the active task: it came from Quick, and goes back there
PLAIN = {"focus": "a focus", "quick": "a quick item", "today": "a block"}  # no notes or steps
STEP = re.compile(r"- \[([ xX>-])\] ")  # under a task: - [ ] open, [x] done, [>] skipped, [-] left
MARKS: dict[str, StepState] = {" ": "open", "x": "done", "X": "done", ">": "skipped", "-": "left"}
BOXES: dict[StepState, str] = {"open": " ", "done": "x", "skipped": ">", "left": "-"}


def render(lists: Lists) -> str:
    lines = ["# Active"]
    match lists.active:
        case FromQuick(task=task):
            lines += [_task_line(task), f"  {HOME_QUICK}"]
        case Task() as task:
            lines += [_task_line(task), *_step_lines(task)]
        case Idle():
            pass
    lines += ["", "# Focus", *(f"- {text}" for text in lists.focus), "", "# Parked"]
    for parked in lists.parked:
        lines.append(_task_line(parked.task))
        lines += [*_note_lines(parked.reason), *_step_lines(parked.task)]
    lines += ["", "# Quick", *(_task_line(task) for task in lists.quick)]
    match lists.plan:
        case Plan(day=day, blocks=planned):
            lines += ["", f"{TODAY} {day.isoformat()}", *(f"- {blocks.text(b)}" for b in planned)]
        case NoPlan():
            pass
    return "\n".join(lines) + "\n"


def _task_line(task: Task) -> str:
    return f"- {shown(task)}"


def _step_lines(task: Task) -> list[str]:
    return [f"  - [{BOXES[step.state]}] {step.text}" for step in task.steps]


def _note_lines(reason: LeftOff | Waiting | Queued) -> list[str]:
    match reason:
        case Waiting(on=on):
            return [f"  {WAITING_ON} {on}"]
        case Queued():
            return [f"  {QUEUED}"]
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
        self.active: Task | FromQuick | Idle = Idle()
        self.parked: list[ParkedTask] = []
        self.focus: list[str] = []
        self.quick: list[Task] = []
        self.plan: Plan | NoPlan = NoPlan()
        self.noted = False  # the last task already has its note

    def lists(self) -> Lists:
        quick = smallest_first(tuple(self.quick))
        return Lists(self.active, tuple(self.parked), tuple(self.focus), quick, self.plan)

    def feed(self, line: str) -> str:
        if not line:
            return ""
        if line.startswith("#"):
            return self._heading(line)
        if not self.section:
            return "text before the first heading"
        if line == "-" or line.startswith("- "):
            return self._task(line[1:].strip())
        if line.startswith(" "):
            return self._indented(line)
        if line.startswith("\t"):
            return "indent with two spaces, not a tab"
        return "glance can't read this line"

    def _indented(self, line: str) -> str:
        """Under a task: a note, or a step at exactly two spaces. A step indented further would
        be a step inside a step, which glance can't keep, so it's refused rather than flattened."""
        text = line.strip()
        if not text.startswith("- "):
            return self._note(text) if line.startswith("  ") else "glance can't read this line"
        if not line.startswith("  - "):
            return "a step goes two spaces in, then - [ ] text (no steps inside steps)"
        return self._step(text)

    def _heading(self, line: str) -> str:
        if line == TODAY or line.startswith(f"{TODAY} "):
            return self._today(line[len(TODAY) :].strip())
        section = HEADINGS.get(line, "")
        if not section:
            return f"unknown heading '{line}'"
        if section in self.seen:
            return f"'{line}' appears twice"
        self.seen.add(section)
        self.section = section
        return ""

    def _today(self, text: str) -> str:
        if "today" in self.seen:
            return f"'{TODAY}' appears twice"
        match blocks.day(text):
            case blocks.Refused(why=why):
                return why
            case day:
                self.plan = Plan(day)
        self.seen.add("today")
        self.section = "today"
        return ""

    def _task(self, text: str) -> str:
        if not sized(text).title:  # "- " alone, or "- ~5m": a size with nothing to size
            return "a task needs a title"
        self.noted = False
        match self.section:
            case "parked":
                self.parked.append(ParkedTask(sized(text), LeftOff()))
            case "quick":
                self.quick.append(sized(text))
            case "focus":
                return self._focus(text)
            case "today":
                return self._block(text)
            case _:
                return self._active(text)
        return ""

    def _active(self, text: str) -> str:
        match self.active:
            case Idle():
                self.active = sized(text)
                return ""
            case Task() | FromQuick():
                return "only one task can be active"

    def _block(self, text: str) -> str:
        """In time order or not, but never overlapping."""
        match self.plan, blocks.read(text):
            case _, blocks.Refused(why=why):
                return why
            case Plan(day=day), Block() as block:
                return self._planned(blocks.add(self.plan, block, day))
            case NoPlan(), _:
                return "a block goes under a Today heading"

    def _planned(self, plan: Plan | blocks.Refused) -> str:
        match plan:
            case blocks.Refused(why=why):
                return why
            case Plan():
                self.plan = plan
                return ""

    def _focus(self, text: str) -> str:
        if len(self.focus) >= FOCUS_SLOTS:
            return f"focus holds at most {FOCUS_SLOTS}"
        self.focus.append(text)
        return ""

    def _note(self, text: str) -> str:
        if self.section == "active":
            return self._home(text)
        if self.section in PLAIN:
            return f"{PLAIN[self.section]} can't have a note"
        if not self.parked or self.noted:
            return "a note goes on its own line under a parked task, one per task"
        match _reason(text):
            case _BadNote(message=message):
                return message
            case LeftOff() | Waiting() | Queued() as reason:
                self.parked[-1] = ParkedTask(self.parked[-1].task, reason)
                self.noted = True
                return ""

    def _home(self, text: str) -> str:
        """Once is enough: a second `home: quick` finds a FromQuick, not a Task."""
        match self.active:
            case Task(steps=()) as task if text.lower() == HOME_QUICK:
                self.active = FromQuick(task)
                return ""
            case Task() if text.lower() == HOME_QUICK:
                return _no_steps("quick")
            case FromQuick():
                return f"a task from quick has only '{HOME_QUICK}' under it, once"
            case _:
                return f"the active task can only have steps or '{HOME_QUICK}' under it"

    def _step(self, text: str) -> str:
        match STEP.split(text, maxsplit=1):
            case ["", mark, words]:
                step = Step(" ".join(words.split()), MARKS[mark])
            case _:
                return "a step looks like '- [ ] text': [x] done, [>] skipped, [-] skipped again"
        match self.section, self.active:
            case "active", Task() as task:
                self.active = replace(task, steps=(*task.steps, step))
            case "parked", _ if self.parked:
                last = self.parked[-1]
                self.parked[-1] = replace(
                    last, task=replace(last.task, steps=(*last.task.steps, step))
                )
            case "active", FromQuick():
                return _no_steps("quick")
            case section, _ if section in PLAIN:
                return _no_steps(section)
            case _:
                return "a step goes under a task"
        return ""


def _no_steps(section: str) -> str:
    return f"{PLAIN[section]} can't have steps"


@dataclass(frozen=True)
class _BadNote:
    message: str


def _reason(text: str) -> LeftOff | Waiting | Queued | _BadNote:
    lowered = text.lower()
    if lowered == QUEUED:
        return Queued()
    if lowered.startswith(WAITING_ON):
        on = text[len(WAITING_ON) :].strip()
        return Waiting(on) if on else _BadNote("waiting on what?")
    if lowered.startswith(LEFT_OFF):
        return LeftOff(text[len(LEFT_OFF) :].strip())
    return _BadNote(f"a note starts with '{WAITING_ON}' or '{LEFT_OFF}', or is '{QUEUED}'")
