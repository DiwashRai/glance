"""Planned blocks: time set aside today. Pure: text in, values out, with today's date passed in.

A block is written `14:00-15:30 PR reviews`, or typed with a length, `14:00 1h deep work`. A `!`
at the end means it must happen today. Blocks on one day never overlap.
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date, time

from app.core.model import Block, NoPlan, Plan

CLOCK = r"([01]?[0-9]|2[0-3]):([0-5][0-9])"
TIMES = re.compile(rf"{CLOCK}(?:-{CLOCK})?", re.ASCII)
LENGTH = re.compile(r"(?:([0-9]{1,2})h)?(?:([0-9]{1,3})m)?", re.ASCII)
DAY = re.compile(r"([1-9][0-9]{3})-(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])", re.ASCII)
MUST = "!"
EXAMPLE = "14:00 1h deep work, or 14:00-15:30 PR reviews"


@dataclass(frozen=True)
class Refused:
    why: str


def read(text: str) -> Block | Refused:
    """Any run of spaces or tabs counts as one, as it does in a typed command."""
    when, _, rest = " ".join(text.split()).partition(" ")
    found = TIMES.fullmatch(when)
    if not found:
        return Refused(f"a block starts with its time: {EXAMPLE}")
    start = time(int(found[1]), int(found[2]))
    match _end(start, found[3], found[4], rest):
        case Refused() as refused:
            return refused
        case _Until(end=end, what=what):
            return _block(start, end, what)


@dataclass(frozen=True)
class _Until:
    end: time
    what: str  # the text after the times


def _block(start: time, end: time, what: str) -> Block | Refused:
    """A name can't start with a length: `14:00-15:00 30m x` would read as both an end and a
    length, so it's refused however it was typed, and what's saved always reads back."""
    named, must = _must(what)
    if not named:
        return Refused(f"what's the block for? {EXAMPLE}")
    first = named.split()[0]
    if LENGTH.fullmatch(first):
        return Refused(f"the name can't start with a length: write 1h30m as one word, {EXAMPLE}")
    if end <= start:
        return Refused("a block ends after it starts, before midnight")
    return Block(start, end, named, must)


def _end(start: time, hour: str, minute: str, rest: str) -> _Until | Refused:
    """The end, given (`-15:30`) or worked out from a length (`1h`, `30m`, `1h30m`), and the
    text after it."""
    if hour:
        return _Until(time(int(hour), int(minute)), rest)
    length, _, what = rest.partition(" ")
    found = LENGTH.fullmatch(length)
    minutes = int(found[1] or 0) * 60 + int(found[2] or 0) if found else 0
    if not minutes:
        return Refused(f"how long? an end or a length: {EXAMPLE}")
    end = start.hour * 60 + start.minute + minutes
    if end >= 24 * 60:
        return Refused("a block ends before midnight: 23:59 at the latest")
    return _Until(time(end // 60, end % 60), what)


def _must(what: str) -> tuple[str, bool]:
    """A `!` on its own at the end, so `ship it!` stays a name."""
    words = what.split()
    if words[-1:] == [MUST]:
        return " ".join(words[:-1]), True
    return " ".join(words), False


def text(block: Block) -> str:
    """`14:00-15:30 PR reviews`, as tasks.md has it."""
    must = f" {MUST}" if block.must else ""
    return f"{times(block)} {block.what}{must}"


def times(block: Block) -> str:
    """`14:00-15:30`"""
    return f"{block.start:%H:%M}-{block.end:%H:%M}"


def day(text: str) -> date | Refused:
    """`2026-10-18`, a real date."""
    found = DAY.fullmatch(text)
    if not found:
        return Refused("the date goes after Today, like '# Today 2026-10-18'")
    year, month, number = int(found[1]), int(found[2]), int(found[3])
    if number > calendar.monthrange(year, month)[1]:
        return Refused(f"{text} isn't a real date")
    return date(year, month, number)


def planned(plan: Plan | NoPlan, today: date) -> tuple[Block, ...]:
    """Today's blocks, by start time. Another day's are stale, so there are none."""
    match plan:
        case Plan(day=planned_for, blocks=blocks) if planned_for == today:
            return blocks
        case Plan() | NoPlan():
            return ()


def add(plan: Plan | NoPlan, block: Block, today: date) -> Plan | Refused:
    """A stale plan is replaced by today's."""
    blocks = planned(plan, today)
    clash = [other for other in blocks if other.start < block.end and block.start < other.end]
    if clash:
        return Refused(f"that overlaps {text(clash[0])}")
    return Plan(today, tuple(sorted((*blocks, block), key=lambda each: each.start)))
