"""Planned blocks: time set aside today. Pure: text in, values out, with the time passed in.

A block is typed in words, `deep work 2pm for 2h`, and written in tasks.md as
`14:00-16:00 deep work` (or by hand with a length, `14:00 2h deep work`). A `!` at the end means
it must happen today. Blocks on one day never overlap: a newer one cuts back the ones it lands on.
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass, replace
from datetime import date, time
from typing import Literal

from app.core.model import Block, NoPlan, Plan

CLOCK = r"([01]?[0-9]|2[0-3]):([0-5][0-9])"
TIMES = re.compile(rf"{CLOCK}(?:-{CLOCK})?", re.ASCII)
LENGTH = re.compile(r"(?:([0-9]{1,2})h)?(?:([0-9]{1,3})m)?", re.ASCII)
SAID = re.compile(r"([0-9]{1,2})(?::([0-5][0-9]))?(am|pm)?", re.ASCII)  # 2pm, 9:30, 14:00
DAY = re.compile(r"([1-9][0-9]{3})-(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])", re.ASCII)
WORD = re.compile(r"\S+")
MUST = "!"
EXAMPLE = "14:00 1h deep work, or 14:00-15:30 PR reviews"  # as tasks.md has them

Kind = Literal["time", "for", "length", "other"]

# How a typed line ends when it's a block, word by word. Anything else is a task: the words
# picked up turn blue as I type, so one that isn't blue says it won't be read.
SHAPES: tuple[tuple[Kind, ...], ...] = (
    ("time", "for", "length"),  # deep work 2pm for 2h
    ("for", "length", "time"),  # deep work for 2h 2pm
)
NAMED_TIMES = {"noon": time(12), "evening": time(19)}


@dataclass(frozen=True)
class Refused:
    why: str


@dataclass(frozen=True)
class Found:
    """A block found in a typed line, and where the words glance picked up for it are in the
    text (its time, `for` and length, and `!`), as (start, end) indexes."""

    block: Block
    marks: tuple[tuple[int, int], ...]


@dataclass(frozen=True)
class NotABlock:
    """It doesn't end like a block: it's a task."""


@dataclass(frozen=True)
class Placed:
    """Today's plan with a new block in it, and each block it cut into with what's left of it."""

    plan: Plan
    cut: tuple[tuple[Block, tuple[Block, ...]], ...] = ()


def typed(text: str, now: time) -> Found | NotABlock | Refused:
    """`deep work 2pm for 2h` or `deep work for 2h 2pm`, then `!` if it must happen. A `!` at the
    end of the name means the same (`run ! 6pm for 1h`), so a name never ends in one: tasks.md
    would read it as the marker. `!!` counts as `!`."""
    words = tuple(WORD.finditer(text))
    end = tuple(word for word in words[-1:] if _is_bang(word))
    body = words[: len(words) - len(end)]
    tail = body[-3:]
    kinds = tuple(_kind(word[0].lower(), now) for word in tail)
    if kinds not in SHAPES:
        return NotABlock()
    named = body[:-3]
    named_bang = tuple(word for word in named[-1:] if _is_bang(word))
    name = " ".join(word[0] for word in named[: len(named) - len(named_bang)])
    bangs = (*named_bang, *end)
    if not name:
        return Refused("what's the block for? its name goes first")
    said = {kind: word[0].lower() for kind, word in zip(kinds, tail, strict=True)}
    (start,) = _times(said["time"], now)
    match _after(start, _minutes(said["length"])):
        case Refused() as refused:
            return refused
        case finish:
            marks = tuple(sorted(word.span() for word in (*tail, *bangs)))
            return Found(Block(start, finish, name, bool(bangs)), marks)


def _kind(said: str, now: time) -> Kind:
    if said == "for":
        return "for"
    if _minutes(said):
        return "length"
    return "time" if _times(said, now) else "other"


def _is_bang(word: re.Match[str]) -> bool:
    return not word[0].strip(MUST)


def _times(said: str, now: time) -> tuple[time, ...]:
    """The time a word names, if it names one. `2pm` and `14:00` are exact, and `noon` and
    `evening` are looked up. `9` or `9:30`, with no am or pm, is the next one after now, or the
    evening one once both have gone. `12` is noon, and `09:00` nine in the morning."""
    found = SAID.fullmatch(said)
    if not found:
        return tuple(at for word, at in NAMED_TIMES.items() if word == said)
    digits, minute, half = found[1], int(found[2] or 0), found[3]
    hour = int(digits)
    if half:
        return (time(hour % 12 + (12 if half == "pm" else 0), minute),) if 1 <= hour <= 12 else ()
    if hour > 23:
        return ()
    morning = time(hour, minute)
    if digits.startswith("0") or not 1 <= hour <= 11:
        return (morning,)
    gone = morning < now.replace(second=0, microsecond=0)
    return (time(hour + 12, minute) if gone else morning,)


def _minutes(length: str) -> int:
    """`1h`, `30m` or `1h30m` in minutes, 0 if it isn't a length."""
    found = LENGTH.fullmatch(length)
    return int(found[1] or 0) * 60 + int(found[2] or 0) if found else 0


def _after(start: time, minutes: int) -> time | Refused:
    """The start is in the refusal, as it may not be the time typed: at 10:00, `9` is 21:00."""
    end = start.hour * 60 + start.minute + minutes
    if end >= 24 * 60:
        return Refused(f"from {start:%H:%M}, that runs past midnight")
    return time(end // 60, end % 60)


def read(text: str) -> Block | Refused:
    """A block as tasks.md has it. Any run of spaces or tabs counts as one."""
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
    named, must = _must(what)
    if not named:
        return Refused(f"what's the block for? {EXAMPLE}")
    if end <= start:
        return Refused("a block ends after it starts, before midnight")
    return Block(start, end, named, must)


def _end(start: time, hour: str, minute: str, rest: str) -> _Until | Refused:
    """The end, given (`-15:30`) or worked out from a length (`1h`, `30m`, `1h30m`), and the
    text after it."""
    if hour:
        return _Until(time(int(hour), int(minute)), rest)
    length, _, what = rest.partition(" ")
    minutes = _minutes(length)
    if not minutes:
        return Refused(f"how long? an end or a length: {EXAMPLE}")
    match _after(start, minutes):
        case Refused() as refused:
            return refused
        case end:
            return _Until(end, what)


def _must(what: str) -> tuple[str, bool]:
    """A `!` (or `!!`) on its own at the end, as when typed, so `ship it!` stays a name."""
    words = what.split()
    if [word.strip(MUST) for word in words[-1:]] == [""]:
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
    """As tasks.md is read: blocks written by hand that overlap are a mistake, so refused. A
    stale plan is replaced by today's."""
    blocks = planned(plan, today)
    clash = [other for other in blocks if _overlap(other, block)]
    if clash:
        return Refused(f"that overlaps {text(clash[0])}")
    return Plan(today, _in_order((*blocks, block)))


def place(plan: Plan | NoPlan, block: Block, today: date) -> Placed | Refused:
    """As a block is typed: the newer one wins. A block it lands on is cut back around it: split
    if it's in the middle, gone if it's covered. One that must happen is never cut: unblock it
    first. A stale plan is replaced by today's."""
    blocks = planned(plan, today)
    hit = tuple(other for other in blocks if _overlap(other, block))
    must = [other for other in hit if other.must]
    if must:
        return Refused(f"{must[0].what} must happen: unblock it first")
    kept = (piece for other in blocks for piece in _around(other, block))
    cut = tuple((other, _around(other, block)) for other in hit)
    return Placed(Plan(today, _in_order((*kept, block))), cut)


def _overlap(one: Block, other: Block) -> bool:
    return one.start < other.end and other.start < one.end


def _around(old: Block, new: Block) -> tuple[Block, ...]:
    """What's left of `old` once `new` is in: the part before it, the part after, both or
    neither. The same name is no different: blocks are never merged or moved."""
    if not _overlap(old, new):
        return (old,)
    before = (replace(old, end=new.start),) if old.start < new.start else ()
    after = (replace(old, start=new.end),) if new.end < old.end else ()
    return (*before, *after)


def _in_order(blocks: tuple[Block, ...]) -> tuple[Block, ...]:
    return tuple(sorted(blocks, key=lambda each: each.start))
