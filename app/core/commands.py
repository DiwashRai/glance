"""A typed line into a command, and a command applied to the lists.

`apply` never fails: it returns the new lists with the events and a message, or a rejection that
says why and changes nothing.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace
from datetime import datetime

from app.core import blocks, highlight, steps
from app.core.model import (
    FOCUS_SLOTS,
    Block,
    CommandWords,
    Event,
    FromQuick,
    Idle,
    LeftOff,
    Lists,
    NoPlan,
    OnStep,
    ParkedTask,
    Plan,
    Queued,
    Star,
    Task,
    Waiting,
    shown,
    size_text,
    sized,
    smallest_first,
    step_line,
    where,
    working,
)


@dataclass(frozen=True)
class New:
    title: str


@dataclass(frozen=True)
class Park:
    """`park` (left off, with an optional note) or `wait` (on something)."""

    reason: LeftOff | Waiting


@dataclass(frozen=True)
class Switch:
    query: str


@dataclass(frozen=True)
class Done:
    query: str = ""  # a Quick item to tick off; empty finishes the active task


@dataclass(frozen=True)
class Focus:
    text: str


@dataclass(frozen=True)
class Unfocus:
    query: str


@dataclass(frozen=True)
class Quick:
    text: str


@dataclass(frozen=True)
class AddStep:
    text: str


@dataclass(frozen=True)
class Skip:
    extra: str = ""


@dataclass(frozen=True)
class Finish:
    extra: str = ""


@dataclass(frozen=True)
class Unblock:
    query: str


@dataclass(frozen=True)
class Remove:
    row: str  # f1, p2, q3: a row on the Focus, Parked or Quick card


@dataclass(frozen=True)
class StarIt:
    """Make a task today's highlight: the active one, or one picked by row or name, as switch
    picks one. Words that match no task are added as a new one, starred."""

    query: str = ""


@dataclass(frozen=True)
class Unstar:
    extra: str = ""


@dataclass(frozen=True)
class Typed:
    """No command word: a block if it ends in a time and a length, else a new task. The text is
    as it was typed, so the words picked up from it can be shown where they are."""

    text: str


@dataclass(frozen=True)
class Ask:
    """A line for an agent: one space first is for the first of `CommandWords.agents`
    (assistant), two or more for the second (chief)."""

    agent: str
    text: str


CardCommand = Focus | Unfocus | Remove  # a goal, or a row on a card
StepCommand = AddStep | Skip | Finish  # the active task's steps
StarCommand = StarIt | Unstar
Command = (
    New | Park | Switch | Done | Quick | Unblock | Typed | CardCommand | StepCommand | StarCommand
)


@dataclass(frozen=True)
class Applied:
    lists: Lists
    events: tuple[Event, ...]
    message: str


@dataclass(frozen=True)
class Rejected:
    reason: str


@dataclass(frozen=True)
class Preview:
    """What a line will do, worked out as it's typed: where the words glance picked up from it
    are, as (start, end) indexes, and a short note."""

    marks: tuple[tuple[int, int], ...] = ()
    note: str = ""
    agent: str = ""  # who a line for an agent goes to
    trouble: bool = False  # the note says something's wrong outside glance: shown in red
    plan: Plan | NoPlan = NoPlan()  # as it would be: not shown, but Enter checks it's the same


def parse_command(text: str, words: CommandWords) -> Command | Ask:
    """A command word first decides, case-insensitively, and the rest is the argument. With no
    command word, it's `Typed`; with spaces first, it's for an agent (`Ask`).

    Any run of whitespace in the argument, line breaks included, becomes one space, so a title or
    note is always a single line and `tasks.md` can always be read back.
    """
    spaces = len(text) - len(text.lstrip(" "))
    if spaces:
        agents = words.agents
        return Ask(agents[min(spaces, len(agents)) - 1], text.strip())
    first, *rest = text.split(maxsplit=1) or [""]
    word = first.lower()
    argument = " ".join(rest[0].split()) if rest else ""
    commands: tuple[tuple[tuple[str, ...], Callable[[str], Command]], ...] = (
        (words.new, New),
        (words.park, lambda note: Park(LeftOff(note))),
        (words.wait, lambda on: Park(Waiting(on))),
        (words.switch, Switch),
        (words.done, Done),
        (words.focus, Focus),
        (words.unfocus, Unfocus),
        (words.quick, Quick),
        (words.step, AddStep),
        (words.skip, Skip),
        (words.finish, Finish),
        (words.unblock, Unblock),
        (words.remove, Remove),
        (words.star, StarIt),
        (words.unstar, Unstar),
    )
    for command_words, command in commands:
        if word in command_words:
            return command(argument)
    return Typed(text)


def spaces_for(agent: str, words: CommandWords) -> int:
    """How many spaces start a line for `agent`, the other way round from `parse_command`: 0 for
    one that lines don't go to."""
    return words.agents.index(agent) + 1 if agent in words.agents else 0


def preview(text: str, words: CommandWords, lists: Lists, now: datetime) -> Preview:
    """A command word is marked, so a task that starts with one (`wait for Sam`) is seen to be
    the command before it runs. A block's time, length and `!` are marked, with what it cuts, a
    new task's `*` is marked, `rm` says what it would remove, as that can't be undone, and `star`
    and `unstar` say what they would do."""
    word = tuple(found.span() for found in blocks.WORD.finditer(text))[:1]
    match parse_command(text, words):
        case Ask(agent=agent):
            return Preview(agent=agent, note=agent)
        case Typed():
            return _preview_block(lists, text, now)
        case New():
            return _preview_star(text, word)
        case StarIt() | Unstar() as star:
            return _preview_said(word, apply(lists, star, now))
        case Remove() as remove:
            match apply(lists, remove, now):
                case Applied(events=events):
                    return Preview(word, f"removes {events[0].title}")
                case Rejected(reason=reason):
                    return Preview(word, reason)
        case _:
            return Preview(word)


def _preview_block(lists: Lists, text: str, now: datetime) -> Preview:
    match blocks.typed(text, now.time()):
        case blocks.NotABlock():
            return _preview_star(text)
        case blocks.Refused(why=why):
            return Preview(note=why)
        case blocks.Found(block=block, marks=marks):
            match blocks.place(lists.plan, block, now.date()):
                case blocks.Refused(why=why):
                    return Preview(marks, why)
                case blocks.Placed(plan=plan, cut=cut):
                    return Preview(marks, _cuts(cut), plan=plan)


def _preview_star(text: str, word: tuple[tuple[int, int], ...] = ()) -> Preview:
    """A new task's line: its command word, if it has one, and its `*`, if it has one."""
    star = highlight.mark_span(text)
    return Preview((*word, *star), "today's highlight" if star else "")


def _preview_said(word: tuple[tuple[int, int], ...], result: Applied | Rejected) -> Preview:
    """What `star` or `unstar` would do, as it will say it."""
    match result:
        case Applied(message=message):
            return Preview(word, message)
        case Rejected(reason=reason):
            return Preview(word, reason)


def _cuts(cut: tuple[tuple[Block, tuple[Block, ...]], ...]) -> str:
    """`trims deep work, replaces review`: the same before Enter and after."""
    return ", ".join(f"{'trims' if left else 'replaces'} {old.what}" for old, left in cut)


def apply(lists: Lists, command: Command, now: datetime) -> Applied | Rejected:
    match command:
        case New() | Quick():
            return _add_command(lists, command, now)
        case Park(reason=reason):
            return _park(lists, reason, now)
        case Switch(query=query):
            return _switch(lists, query, now)
        case Done(query=query):
            return _done(lists, query, now)
        case Focus() | Unfocus() | Remove():
            return _card_command(lists, command, now)
        case AddStep() | Skip() | Finish():
            return _step_command(lists, command, now)
        case Typed(text=text):
            return _typed(lists, text, now)
        case Unblock(query=query):
            return _unblock(lists, query, now)
        case StarIt() | Unstar():
            return _star_command(lists, command, now)


def _add_command(lists: Lists, command: New | Quick, now: datetime) -> Applied | Rejected:
    match command:
        case New(title=title):
            return _new(lists, title, now)
        case Quick(text=text):
            return _quick(lists, text, now)


def _set_aside(lists: Lists, reason: LeftOff | Waiting, now: datetime) -> Applied:
    """The lists with the active task (if any) put away, its event, and what to say about it. A
    Quick item put away with no note goes back to Quick; with a note, or waiting, it's become a
    real task, so it goes on top of Parked like any other."""
    match lists.active:
        case Idle():
            return Applied(lists, (), "")
        case FromQuick(task=task) if reason == LeftOff():
            back = replace(lists, active=Idle(), quick=smallest_first((*lists.quick, task)))
            event = Event(now, "parked", task.title, "back in quick")
            return Applied(back, (event,), f"put {shown(task)} back in quick")
        case FromQuick(task=task) | (Task() as task):
            aside = replace(lists, active=Idle(), parked=(ParkedTask(task, reason), *lists.parked))
            return Applied(aside, (_parked_event(task, reason, now),), _parked_said(task, reason))


def _parked_event(task: Task, reason: LeftOff | Waiting, now: datetime) -> Event:
    match reason:
        case Waiting(on=on):
            return Event(now, "waiting", task.title, f"on {on}")
        case LeftOff(note=""):
            return Event(now, "parked", task.title)
        case LeftOff(note=note):
            return Event(now, "parked", task.title, f"left off: {note}")


def _parked_said(task: Task, reason: LeftOff | Waiting) -> str:
    match reason:
        case Waiting(on=on):
            return f"{shown(task)} is waiting on {on}"
        case LeftOff():
            return f"parked {shown(task)}"


def _and(said: str) -> str:
    return f" · {said}" if said else ""


def _new(lists: Lists, title: str, now: datetime) -> Applied | Rejected:
    """At the bottom of the queue, or at the top as today's highlight with a `*` at the end."""
    text, star = highlight.marked(title)
    task = sized(text)
    if not task.title:
        return Rejected("a task needs a title")
    if star:
        return _new_star(lists, task, now)
    queued = replace(lists, parked=(*lists.parked, ParkedTask(task, Queued())))
    row = f"p{len(queued.parked)}"
    said = f"added {shown(task)} to the queue as {row} · s {row} to start it"
    return Applied(queued, (Event(now, "added", task.title, "to the queue"),), said)


def _new_star(lists: Lists, task: Task, now: datetime) -> Applied:
    star = _starring(lists, task, now)
    queued = replace(star.lists, parked=(ParkedTask(star.task, Queued()), *star.lists.parked))
    added = Event(now, "added", task.title, "to the queue")
    said = f"added {shown(task)} to the queue as p1 · ★ today's highlight{star.was}"
    said += " · s p1 to start it"
    return Applied(queued, (added, *star.events), said)


@dataclass(frozen=True)
class _Starring:
    """The lists with no star left on them, the task with today's, and what was starred before."""

    lists: Lists
    task: Task
    events: tuple[Event, ...]
    was: str  # " (was: reply to Sam)", or ""


def _starring(lists: Lists, task: Task, now: datetime) -> _Starring:
    before = tuple(other for other in highlight.starred(lists) if other != task)
    unstarred = tuple(Event(now, "unstarred", other.title, f"for {task.title}") for other in before)
    events = (*unstarred, Event(now, "starred", task.title))
    was = "".join(f" (was: {shown(other)})" for other in before)
    starred = replace(task, star=Star(now.date()))
    return _Starring(highlight.cleared(lists), starred, events, was)


def _star_command(lists: Lists, command: StarCommand, now: datetime) -> Applied | Rejected:
    match command:
        case Unstar(extra=extra) if extra:
            return Rejected("unstar takes the star off: type just unstar")
        case Unstar():
            return _unstar(lists, now)
        case StarIt(query=""):
            return _star_active(lists, now)
        case StarIt(query=query):
            return _star_query(lists, query, now)


def _unstar(lists: Lists, now: datetime) -> Applied | Rejected:
    starred = highlight.starred(lists)
    if not starred:
        return Rejected("nothing is starred")
    task = starred[0]
    event = Event(now, "unstarred", task.title)
    return Applied(highlight.cleared(lists), (event,), f"took the star off {shown(task)}")


def _star_active(lists: Lists, now: datetime) -> Applied | Rejected:
    match lists.active:
        case Idle():
            return Rejected("nothing is active: star p<number> stars a queued task")
        case FromQuick():
            return Rejected(highlight.NOT_QUICK)
        case Task(star=star) as task if star == Star(now.date()):
            return Rejected(f"{shown(task)} is already today's highlight")
        case Task() as task:
            star = _starring(lists, task, now)
            said = f"★ {shown(task)} is today's highlight{star.was}"
            return Applied(replace(star.lists, active=star.task), star.events, said)


def _star_parked(lists: Lists, index: int, now: datetime) -> Applied | Rejected:
    """To the top of the queue, as it's the first thing to pick up."""
    chosen = lists.parked[index]
    if index == 0 and chosen.task.star == Star(now.date()):
        return Rejected(f"{shown(chosen.task)} is already today's highlight")
    star = _starring(replace(lists, parked=_without(lists.parked, index)), chosen.task, now)
    parked = (replace(chosen, task=star.task), *star.lists.parked)
    said = f"★ {shown(chosen.task)} is today's highlight{star.was}, now p1"
    return Applied(replace(star.lists, parked=parked), star.events, said)


def _star_query(lists: Lists, query: str, now: datetime) -> Applied | Rejected:
    """`p2` is the queue's row 2 and `q2` is refused. Other words are looked for in the active
    task, the queue and Quick, as switch does; words that match none are a new task."""
    if QUICK_ROW.fullmatch(query):
        return Rejected(highlight.NOT_QUICK)
    if PARKED_ROW.fullmatch(query):
        match _row(query[1:], len(lists.parked), f"there's no {query.lower()} in the queue"):
            case Rejected() as rejected:
                return rejected
            case _Picked(index=index):
                return _star_parked(lists, index, now)
    active = tuple(("active", task.title) for task in highlight.held(lists.active))
    rows = (*active, *_numbered((item.task.title for item in lists.parked), "p"))
    rows += _numbered((task.title for task in lists.quick), "q")
    hits = [i for i, (_, title) in enumerate(rows) if _matches(query, title)]
    match hits:
        case [index]:
            return _star_at(lists, index - len(active), now)
        case []:
            return _star_row_or_new(lists, query, now)
        case _:
            options = ", ".join(f"{rows[i][0]} {rows[i][1]}" for i in hits)
            return Rejected(f"'{query}' matches {len(hits)}: {options}")


def _star_at(lists: Lists, index: int, now: datetime) -> Applied | Rejected:
    """-1 is the active task, then the queue's rows from 0, then Quick's."""
    if index < 0:
        return _star_active(lists, now)
    if index < len(lists.parked):
        return _star_parked(lists, index, now)
    return Rejected(highlight.NOT_QUICK)


def _star_row_or_new(lists: Lists, query: str, now: datetime) -> Applied | Rejected:
    """A number that names no task is the queue's row, if there's one."""
    if _is_number(query):
        match _row(query, len(lists.parked), ""):
            case _Picked(index=index):
                return _star_parked(lists, index, now)
            case Rejected():
                pass
    return _new(lists, f"{query} {highlight.MARK}", now)


def _park(lists: Lists, reason: LeftOff | Waiting, now: datetime) -> Applied | Rejected:
    if reason == Waiting(""):
        return Rejected("wait on what?")
    match lists.active:
        case Idle():
            return Rejected("nothing is active")
        case FromQuick() | Task():
            return _set_aside(lists, reason, now)


def _done(lists: Lists, query: str, now: datetime) -> Applied | Rejected:
    """The current step if the task has steps, else the task. With no step left to tick (all
    done, or only skipped ones left), done finishes it: so the last step takes a second done."""
    if query:
        return _tick(lists, query, now)
    match working(lists.active):
        case Idle():
            return Rejected("nothing is active")
        case Task() as task:
            match steps.tick(task):
                case steps.Moved(task=moved, step=step, said=said):
                    ticked = Event(now, "ticked", task.title, step)
                    return Applied(replace(lists, active=moved), (ticked,), said)
                case steps.NoStep():
                    return _finish(lists, task, now)


def _finish(lists: Lists, task: Task, now: datetime) -> Applied:
    star = highlight.said(task, now.date())
    leftover = (*steps.leftover(task), *((f"{star} done",) if star else ()))
    finished = Event(now, "finished", task.title, ", ".join(leftover))
    said = " · ".join((f"finished {shown(task)}", *leftover))
    return Applied(replace(lists, active=Idle()), (finished,), said)


def _step_command(lists: Lists, command: StepCommand, now: datetime) -> Applied | Rejected:
    match command, lists.active:
        case _, Idle():
            return Rejected("nothing is active")
        case AddStep(text=""), _:
            return Rejected("step what? for example: step rerun CI with trace")
        case AddStep(text=text), FromQuick(task=task):
            return _add_step(lists, task, text, " · it's a task now, not a quick item")
        case AddStep(text=text), Task() as task:
            return _add_step(lists, task, text, "")
        case Skip(extra=extra), _ if extra:
            return Rejected("skip moves past the current step: type just skip")
        case Finish(extra=extra), _ if extra:
            return Rejected("finish finishes the active task: type just finish")
        case Skip(), FromQuick(task=task) | (Task() as task):
            return _skip(lists, task, now)
        case Finish(), FromQuick(task=task) | (Task() as task):
            return _finish(lists, task, now)


def _add_step(lists: Lists, task: Task, text: str, real: str) -> Applied:
    """A Quick item given steps has become a real task (it's no longer a FromQuick): parked, it
    goes to Parked."""
    stepped = steps.add(task, text)
    said = f"added step {len(stepped.steps)}: {text}{real}"
    return Applied(replace(lists, active=stepped), (), said)


def _skip(lists: Lists, task: Task, now: datetime) -> Applied | Rejected:
    match steps.skip(task):
        case steps.Moved(task=moved, step=step, said=said):
            skipped = Event(now, "skipped", task.title, step)
            return Applied(replace(lists, active=moved), (skipped,), said)
        case steps.NoStep(why=why):
            return Rejected(why)


def _card_command(lists: Lists, command: CardCommand, now: datetime) -> Applied | Rejected:
    match command:
        case Focus(text=text):
            return _focus(lists, text, now)
        case Unfocus(query=query):
            return _unfocus(lists, query, now)
        case Remove(row=row):
            return _remove(lists, row, now)


def _remove(lists: Lists, row: str, now: datetime) -> Applied | Rejected:
    """`rm f1`, `rm p2`, `rm q3`: a row off the Focus, Parked or Quick card, without starting or
    finishing it. Only by its row, as with `done q2`: it can't be undone, so glance never guesses
    one from a name."""
    found = CARD_ROW.fullmatch(row)
    if not found:
        return Rejected("rm f1, p1 or q1")
    card, digits = found[1].lower(), found[2]
    if card == "f":
        return _unfocus(lists, digits, now)
    parked = card == "p"
    tasks = tuple(item.task for item in lists.parked) if parked else lists.quick
    name = "parked" if parked else "quick"
    match _row(digits, len(tasks), f"there's no {card}{digits} in {name}"):
        case Rejected() as rejected:
            return rejected
        case _Picked(index=index):
            kept = (
                replace(lists, parked=_without(lists.parked, index))
                if parked
                else replace(lists, quick=_without(lists.quick, index))
            )
            task = tasks[index]
            removed = Event(now, "removed", task.title, f"from {name}")
            return Applied(kept, (removed,), f"removed {shown(task)} from {name}")


def _tick(lists: Lists, query: str, now: datetime) -> Applied | Rejected:
    """`done q2` ticks a Quick item off without making it active first. Only by its row: a tick
    can't be undone, so glance never guesses one from a name."""
    if not QUICK_ROW.fullmatch(query):
        return Rejected("done ticks the current step; done q<number> ticks off a quick item")
    match _quick_row(query, lists.quick):
        case Rejected() as rejected:
            return rejected
        case _Picked(index=index):
            task = lists.quick[index]
            ticked = replace(lists, quick=_without(lists.quick, index))
            crossed = Event(now, "crossed", task.title)  # not "finished": Active carries on
            return Applied(ticked, (crossed,), f"finished {shown(task)}")


def _quick(lists: Lists, text: str, now: datetime) -> Applied | Rejected:
    task = sized(text)
    if not task.title:
        return Rejected("quick what? for example: quick merge 1129 ~3m")
    added = replace(lists, quick=smallest_first((*lists.quick, task)))
    event = Event(now, "added", task.title, size_text(task))
    return Applied(added, (event,), f"added {shown(task)} to quick")


QUICK_ROW = re.compile(r"[qQ][0-9]+")  # a Quick row as the card labels it: q1, q2…
PARKED_ROW = re.compile(r"[pP][0-9]+")  # a queue row, as rm names it: p1, p2…
CARD_ROW = re.compile(r"([fpqFPQ])([0-9]+)")  # for rm: f1 (focus), p1 (parked), q1 (quick)


@dataclass(frozen=True)
class _Picked:
    index: int


def _numbered(titles: Iterable[str], prefix: str = "") -> tuple[tuple[str, str], ...]:
    """Each title with its row label on the card: 1, 2… or q1, q2…"""
    return tuple((f"{prefix}{number}", title) for number, title in enumerate(titles, 1))


def _is_number(query: str) -> bool:
    return bool(re.fullmatch(r"[0-9]+", query))


def _row(digits: str, count: int, refusal: str) -> _Picked | Rejected:
    """The row a number names on the card (`01` is row 1), or the refusal if there's no such
    row. Long numbers are never rows, and never converted."""
    number = int(digits) if len(digits) <= 6 else 0
    return _Picked(number - 1) if 1 <= number <= count else Rejected(refusal)


def _matches(query: str, title: str) -> bool:
    """Text matches anywhere in a title. A number only matches a whole word: 1129, not 2."""
    if _is_number(query):
        return query in re.findall(r"\w+", title)
    return query.lower() in title.lower()


def _pick(rows: tuple[tuple[str, str], ...], query: str, refusal: str) -> _Picked | Rejected:
    """A title match first, then a row number, so `s 1129` finds the ticket rather than row 1129."""
    hits = [i for i, (_, title) in enumerate(rows) if _matches(query, title)]
    if len(hits) == 1:
        return _Picked(hits[0])
    if hits:
        options = ", ".join(f"{rows[i][0]} {rows[i][1]}" for i in hits)
        return Rejected(f"'{query}' matches {len(hits)}: {options}")
    return _row(query, len(rows), refusal) if _is_number(query) else Rejected(refusal)


def _row_or_name(rows: tuple[tuple[str, str], ...], query: str, refusal: str) -> _Picked | Rejected:
    """A number is always the row on the card, never part of a name; other text is a name."""
    return _row(query, len(rows), refusal) if _is_number(query) else _pick(rows, query, refusal)


def _quick_row(query: str, quick: tuple[Task, ...]) -> _Picked | Rejected:
    """`q2` is always Quick's row 2, never a title with "q2" in it, and a row that isn't there is
    refused rather than guessed."""
    return _row(query[1:], len(quick), f"there's no {query.lower()} in quick")


def _without[T](items: tuple[T, ...], index: int) -> tuple[T, ...]:
    return (*items[:index], *items[index + 1 :])


def _switch(lists: Lists, query: str, now: datetime) -> Applied | Rejected:
    if not query:
        return Rejected("switch to what?")
    parked = len(lists.parked)
    match _switch_row(lists, query):
        case Rejected() as rejected:
            return rejected
        case _Picked(index=index) if index < parked:
            chosen = lists.parked[index]
            rest = replace(lists, parked=_without(lists.parked, index))
            return _resume(rest, chosen.task, chosen.task, _reminder(chosen), now)
        case _Picked(index=index):
            task = lists.quick[index - parked]
            rest = replace(lists, quick=_without(lists.quick, index - parked))
            return _resume(rest, FromQuick(task), task, "", now)


def _switch_row(lists: Lists, query: str) -> _Picked | Rejected:
    """One index across Parked, then Quick. `p2` and `q2` are always row 2 of their card. A
    number only looks at Parked, whose rows are numbered. Other text searches both."""
    parked = _numbered(item.task.title for item in lists.parked)
    if PARKED_ROW.fullmatch(query):
        return _row(query[1:], len(parked), f"there's no {query.lower()} in the queue")
    if QUICK_ROW.fullmatch(query):
        match _quick_row(query, lists.quick):
            case _Picked(index=index):
                return _Picked(len(parked) + index)
            case Rejected() as rejected:
                return rejected
    if _is_number(query):
        refusal = f"no parked task matches '{query}' (quick items: s q<number>)"
        return _pick(parked, query, refusal)
    quick = _numbered((task.title for task in lists.quick), "q")
    return _pick((*parked, *quick), query, f"no task matches '{query}'")


def _resume(
    rest: Lists, active: Task | FromQuick, task: Task, reminder: str, now: datetime
) -> Applied:
    """`rest` has the chosen task taken out; the active one is put away, then `active` (the
    chosen task, marked if it came from Quick) takes its place."""
    aside = _set_aside(rest, LeftOff(), now)
    message = f"switched to {shown(task)}{_and(aside.message)}{reminder}"
    events = (*aside.events, Event(now, "resumed", task.title))
    return Applied(replace(aside.lists, active=active), events, message)


def _reminder(chosen: ParkedTask) -> str:
    """What the task was parked with, so switching back to it says where I was. With no note,
    its step is the note."""
    task = chosen.task
    match chosen.reason, where(task):
        case Waiting(on=on), _:
            return f" · was waiting on {on}"
        case LeftOff(note="") | Queued(), OnStep():
            return f" · on {step_line(task)}"
        case LeftOff(note="") | Queued(), _:
            return _and(step_line(task))  # "" with no steps
        case LeftOff(note=note), _:
            return f" · left off: {note}"


def _focus(lists: Lists, text: str, now: datetime) -> Applied | Rejected:
    if not text:
        return Rejected("focus on what?")
    if text.lower() in (goal.lower() for goal in lists.focus):
        return Rejected(f"already focusing on {text}")
    if len(lists.focus) >= FOCUS_SLOTS:
        return Rejected("focus is full: unfocus one first, by number or name")
    focused = replace(lists, focus=(*lists.focus, text))
    return Applied(focused, (Event(now, "focused", text),), f"focusing on {text}")


def _unfocus(lists: Lists, query: str, now: datetime) -> Applied | Rejected:
    """A number is always the row on the card: "unfocus 2" must never remove "ship phase 2" from
    row 1, since the goal is gone once it's saved."""
    if not query:
        return Rejected("unfocus which? its number or name")
    match _row_or_name(_numbered(lists.focus), query, f"no focus matches '{query}'"):
        case Rejected() as rejected:
            return rejected
        case _Picked(index=index):
            text = lists.focus[index]
            return Applied(
                replace(lists, focus=_without(lists.focus, index)),
                (Event(now, "unfocused", text),),
                f"unfocused {text}",
            )


def _typed(lists: Lists, text: str, now: datetime) -> Applied | Rejected:
    match blocks.typed(text, now.time()):
        case blocks.NotABlock():
            return _new(lists, " ".join(text.split()), now)
        case blocks.Refused(why=why):
            return Rejected(why)
        case blocks.Found(block=block):
            return _place(lists, block, now)


def _place(lists: Lists, block: Block, now: datetime) -> Applied | Rejected:
    match blocks.place(lists.plan, block, now.date()):
        case blocks.Refused(why=why):
            return Rejected(why)
        case blocks.Placed(plan=plan, cut=cut):
            event = Event(now, "planned", block.what, blocks.times(block))
            said = f"planned {_said(block)}{_and(_cuts(cut))}"
            return Applied(replace(lists, plan=plan), (event,), said)


def _said(block: Block) -> str:
    """`deep work 14:00-15:30`, and whether it must happen."""
    must = " · must happen today" if block.must else ""
    return f"{block.what} {blocks.times(block)}{must}"


def _unblock(lists: Lists, query: str, now: datetime) -> Applied | Rejected:
    """By its number in time order, or its name, like unfocus. Its times go with its name, so
    when two share a name, the choice says which is which: `1 deep work 09:00-11:00`."""
    planned = blocks.planned(lists.plan, now.date())
    if not query:
        return Rejected("unblock which? its number or name")
    if not planned:
        return Rejected("nothing is planned today")
    names = _numbered(f"{block.what} {blocks.times(block)}" for block in planned)
    match _row_or_name(names, query, f"no block today matches '{query}'"):
        case Rejected() as rejected:
            return rejected
        case _Picked(index=index):
            block = planned[index]
            plan = Plan(now.date(), _without(planned, index))
            event = Event(now, "unplanned", block.what, blocks.times(block))
            return Applied(replace(lists, plan=plan), (event,), f"unblocked {_said(block)}")
