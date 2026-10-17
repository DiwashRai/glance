"""A task's steps: an ordered checklist, one level deep.

The current step is the first open one. Once none are open, glance comes back round to the
skipped ones; a skipped step skipped again is left, and glance stops coming back to it. With no
current step (every step done or left), `done` finishes the task.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal

from app.core.model import (
    AllDone,
    BackTo,
    NoSteps,
    OnlyLeft,
    OnStep,
    Step,
    Task,
    shown,
    step_line,
    where,
)

Move = Literal["done", "skipped", "left"]
SAID: dict[Move, str] = {"done": "done", "skipped": "skipped", "left": "skipped again"}


@dataclass(frozen=True)
class Moved:
    """The task after its current step was ticked or skipped, and what to say."""

    task: Task
    step: str
    said: str


@dataclass(frozen=True)
class NoStep:
    """No step is current, so there's nothing to tick or skip. `why` says so."""

    why: str


def add(task: Task, text: str) -> Task:
    return replace(task, steps=(*task.steps, Step(text)))


def tick(task: Task) -> Moved | NoStep:
    match where(task):
        case OnStep(index=index) | BackTo(index=index):
            return _move(task, index, "done")
        case OnlyLeft() | AllDone() | NoSteps():
            return NoStep(_ending(task))


def skip(task: Task) -> Moved | NoStep:
    """An open step is skipped, and comes back round; a skipped one is left."""
    match where(task):
        case OnStep(index=index):
            return _move(task, index, "skipped")
        case BackTo(index=index):
            return _move(task, index, "left")
        case NoSteps():
            return NoStep("no steps to skip · step <text> adds one")
        case OnlyLeft() | AllDone():
            return NoStep(f"nothing to skip · {_ending(task)}")


def leftover(task: Task) -> tuple[str, ...]:
    """What finishing leaves undone: ("1 step skipped",), ("2 steps not done",), or ()."""
    counts = (
        (sum(step.state == "open" for step in task.steps), "not done"),
        (sum(step.state in ("skipped", "left") for step in task.steps), "skipped"),
    )
    return tuple(f"{n} step{'s' if n > 1 else ''} {what}" for n, what in counts if n)


def _move(task: Task, index: int, move: Move) -> Moved:
    step = task.steps[index]
    steps = (*task.steps[:index], replace(step, state=move), *task.steps[index + 1 :])
    moved = replace(task, steps=steps)
    return Moved(moved, step.text, f"{SAID[move]}: {step.text} · {_next(moved)}")


def _next(task: Task) -> str:
    """What comes after a tick or a skip, with what to type when the steps run out."""
    match where(task):
        case OnStep():
            return f"next: {step_line(task)}"
        case BackTo():
            return step_line(task)
        case OnlyLeft() | AllDone() | NoSteps():
            return _ending(task)


def _ending(task: Task) -> str:
    """What to type once no step is current."""
    match where(task):
        case OnlyLeft():
            return f"{step_line(task)} · done to finish anyway"
        case AllDone() | NoSteps() | OnStep() | BackTo():
            return f"{step_line(task)} · done again to finish {shown(task)}"
