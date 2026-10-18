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

from app.core.model import Block, NoPlan, Plan

CLOCK = r"([01]?[0-9]|2[0-3]):([0-5][0-9])"
TIMES = re.compile(rf"{CLOCK}(?:-{CLOCK})?", re.ASCII)
LENGTH = re.compile(r"(?:([0-9]{1,2})h)?(?:([0-9]{1,3})m)?", re.ASCII)
SAID = re.compile(r"([0-9]{1,2})(?::([0-5][0-9]))?(am|pm)?", re.ASCII)  # 2pm, 9:30, 14:00
DAY = re.compile(r"([1-9][0-9]{3})-(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])", re.ASCII)
WORD = re.compile(r"\S+")
# 1h, 90, 1.5h, -1h, 2hrs, 1h30: like a length, so a block, if not one glance can read. Each
# digit can only be read one way, so a long run of them is quick to turn down.
HOURS = ("h", "hr", "hrs", "hour", "hours")
MINUTES = ("m", "min", "mins", "minute", "minutes")
UNITS = (*HOURS, *MINUTES)
LIKE_LENGTH = re.compile(
    rf"[-+.]?\d+(?:[.,]\d+)*"  # a number
    rf"(?:(?:{'|'.join(HOURS)})(?:\d+(?:{'|'.join(MINUTES)})?)?|{'|'.join(MINUTES)})?"  # 1h30m
)
MUST = "!"
EXAMPLE = "14:00 1h deep work, or 14:00-15:30 PR reviews"  # as tasks.md has them
WHEN = "what time? like 2pm or 14:30"  # short: it's shown beside the text box as I type
ONE_WORD = "write the length as one word, like 1h30m"


@dataclass(frozen=True)
class Refused:
    why: str


@dataclass(frozen=True)
class Found:
    """A block found in a typed line, and where the words glance picked up for it are in the
    text (its time, `for` and length, an `at`, a `!`), as (start, end) indexes."""

    block: Block
    marks: tuple[tuple[int, int], ...]


@dataclass(frozen=True)
class NotABlock:
    """It doesn't end in `for` and a length: it's a task."""


@dataclass(frozen=True)
class Placed:
    """Today's plan with a new block in it, and each block it cut into with what's left of it."""

    plan: Plan
    cut: tuple[tuple[Block, tuple[Block, ...]], ...] = ()


def typed(text: str, now: time) -> Found | NotABlock | Refused:
    """`deep work 2pm for 2h`, `deep work at 2pm for 2h` or `deep work for 2h 2pm`, then `!` if
    it must happen. Ending in `for` and something like a length makes it a block, so a bad time
    or length is refused, not made into a task."""
    words = _words(text)
    bang = tuple(word for word in words[-1:] if not word.text.strip(MUST))
    match _parts(words[: len(words) - len(bang)]):
        case _Parts() as parts:
            return _found(parts, bang, now)
        case NotABlock() | Refused() as other:
            return other


@dataclass(frozen=True)
class _Word:
    text: str
    start: int
    end: int


def _words(text: str) -> tuple[_Word, ...]:
    """Each word and where it is. `!`s stuck to the last word are a `!` of their own (`1h!`); a
    line that turns out to be a task keeps its text as typed."""
    words = [_Word(found[0], found.start(), found.end()) for found in WORD.finditer(text)]
    stuck = [word for word in words[-1:] if word.text.rstrip(MUST) not in ("", word.text)]
    apart = [piece for word in stuck for piece in _unstuck(word)]
    return (*words[: len(words) - len(stuck)], *apart)


def _unstuck(word: _Word) -> tuple[_Word, _Word]:
    body = word.text.rstrip(MUST)
    split = word.start + len(body)
    return _Word(body, word.start, split), _Word(MUST, split, word.end)


@dataclass(frozen=True)
class _Parts:
    name: tuple[_Word, ...]
    clock: _Word
    length: tuple[_Word, _Word]  # `for` and the length
    at: tuple[_Word, ...] = ()  # `at` before the time


def _parts(words: tuple[_Word, ...]) -> _Parts | NotABlock | Refused:
    """The time and the length off the end: `(at) 2pm for 2h`, or `for 2h (at) 2pm`."""
    said = [word.text.lower() for word in words]
    if said[-2:-1] == ["for"] and _like_length(said[-1]):
        if len(words) < 3:
            return Refused(WHEN)
        at = 1 if said[-4:-3] == ["at"] else 0
        return _Parts(words[: -3 - at], words[-3], (words[-2], words[-1]), words[-3 - at : -3])
    at = 1 if said[-2:-1] == ["at"] else 0
    if said[-3 - at : -2 - at] == ["for"] and _like_length(said[-2 - at]):
        return _time_last(words, at)
    return NotABlock()


def _time_last(words: tuple[_Word, ...], at: int) -> _Parts | NotABlock | Refused:
    """`for 2h 2pm`. A unit last (`for 2 hours`) is a length written as two words. After a bare
    number, a last word that isn't a time is the end of a task's title (`dinner for 4 tonight`);
    after anything more like a length (`for 1h noon`), it's a time glance can't read."""
    last = words[-1].text.lower()
    length = (words[-3 - at], words[-2 - at])
    if last in UNITS:
        return Refused(ONE_WORD)
    if not last[:1].isdigit():
        return NotABlock() if length[1].text.isdigit() else Refused(WHEN)
    return _Parts(words[: -3 - at], words[-1], length, words[-2 : -2 + at])


def _found(parts: _Parts, bang: tuple[_Word, ...], now: time) -> Found | Refused:
    """A `!` at the end of the name means it must happen too, so `run ! 6pm for 1h` is the same
    as `run 6pm for 1h !`: a name never ends in `!` on its own, as tasks.md couldn't read it."""
    named_bang = tuple(word for word in parts.name[-1:] if not word.text.strip(MUST))
    name = " ".join(word.text for word in parts.name[: len(parts.name) - len(named_bang)])
    picked = (*parts.at, parts.clock, *parts.length, *named_bang, *bang)
    match _from(parts, name, now, bool(bang or named_bang)):
        case Block() as block:
            return Found(block, tuple(sorted((word.start, word.end) for word in picked)))
        case Refused() as refused:
            return refused


def _from(parts: _Parts, name: str, now: time, must: bool) -> Block | Refused:
    """The time first: in `lunch for 1h`, it's the time that's missing, not the name."""
    clock = parts.clock.text.lower()
    if _is_length(clock):
        return Refused(ONE_WORD)
    match _clock(clock, now):
        case Refused() as refused:
            return refused
        case start:
            return _named(name, start, parts.length[1].text.lower(), must)


def _named(name: str, start: time, length: str, must: bool) -> Block | Refused:
    if not name:
        return Refused("what's the block for? its name goes first")
    minutes = _minutes(length)
    if not minutes:
        return Refused("how long? like for 1h or 90m")
    match _after(start, minutes):
        case Refused() as refused:
            return refused
        case end:
            return Block(start, end, name, must)


def _clock(said: str, now: time) -> time | Refused:
    """`2pm` and `14:00` are exact. `9` or `9:30`, with no am or pm, is the next one after now,
    or the evening one once both have gone. `12` is noon, and `09:00` nine in the morning."""
    found = SAID.fullmatch(said)
    if not found:
        return Refused(WHEN)
    digits, minute, half = found[1], int(found[2] or 0), found[3]
    hour = int(digits)
    if half:
        if not 1 <= hour <= 12:
            return Refused(WHEN)
        return time(hour % 12 + (12 if half == "pm" else 0), minute)
    if hour > 23:
        return Refused(WHEN)
    morning = time(hour, minute)
    if digits.startswith("0") or not 1 <= hour <= 11:
        return morning
    return morning if morning >= now.replace(second=0, microsecond=0) else time(hour + 12, minute)


def _like_length(said: str) -> bool:
    """A number, perhaps with a unit: `1h`, but also `90`, `1.5h`, `-1h` or `2hrs`, which are
    refused with how to write it rather than becoming part of a task's title."""
    return bool(LIKE_LENGTH.fullmatch(said))


def _is_length(said: str) -> bool:
    return bool(said) and bool(LENGTH.fullmatch(said))


def _minutes(length: str) -> int:
    """`1h`, `30m` or `1h30m` in minutes, 0 if it isn't a length."""
    found = LENGTH.fullmatch(length)
    return int(found[1] or 0) * 60 + int(found[2] or 0) if found else 0


def _after(start: time, minutes: int) -> time | Refused:
    """The start is in the refusal, as it may not be the time typed: at 10:00, `9` is 21:00."""
    end = start.hour * 60 + start.minute + minutes
    if end >= 24 * 60:
        return Refused(f"from {start:%H:%M}, that runs past 23:59")
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
