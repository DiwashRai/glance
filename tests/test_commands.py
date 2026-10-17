from datetime import datetime, timedelta, timezone

import pytest

from app.core.commands import (
    Applied,
    Command,
    Done,
    Focus,
    New,
    Park,
    Rejected,
    Switch,
    Unfocus,
    Unknown,
    Wait,
    apply,
    parse_command,
)
from app.core.model import CommandWords, Event, Idle, LeftOff, Lists, ParkedTask, Task, Waiting
from app.core.tasks_md import parse, render

NOW = datetime(2026, 10, 17, 9, 58, 40, tzinfo=timezone(timedelta(hours=1)))
WORDS = CommandWords()

ACTIVE = Task("1135 fix token refresh race")
WAITING = ParkedTask(Task("1129 password reset flow"), Waiting("review"))
LEFT = ParkedTask(Task("tidy logging config"), LeftOff("half done"))
DAY = Lists(ACTIVE, (WAITING, LEFT))
IDLE_DAY = Lists(Idle(), (WAITING, LEFT))


def run(lists: Lists, text: str) -> Applied | Rejected:
    return apply(lists, parse_command(text, WORDS), NOW)


def applied(lists: Lists, text: str) -> Applied:
    match run(lists, text):
        case Applied() as result:
            return result
        case Rejected(reason=reason):
            pytest.fail(f"rejected: {reason}")


@pytest.mark.parametrize(
    ("text", "command"),
    [
        ("new fix the build", New("fix the build")),
        ("PAUSE retry loop", Park("retry loop")),
        ("shelve", Park("")),
        ("wait CI run", Wait("CI run")),
        ("s 1129", Switch("1129")),
        ("d", Done()),
        ("done 1129", Done("1129")),
        ("new\tfix  the   build ", New("fix the build")),
        ("Focus fix the vulnerabilities", Focus("fix the vulnerabilities")),
        ("unfocus 2", Unfocus("2")),
        ("hello there", Unknown("hello")),
        ("   ", Unknown("")),
    ],
)
def test_parses_the_first_word(text: str, command: Command) -> None:
    assert parse_command(text, WORDS) == command


@pytest.mark.parametrize("text", ["new a\n- b", f"new a{chr(0x2028)}- b"])
def test_line_breaks_become_one_space_so_tasks_md_reads_back(text: str) -> None:
    result = applied(Lists(), text)
    assert result.lists.active == Task("a - b")
    assert parse(render(result.lists)) == result.lists


def test_words_come_from_settings() -> None:
    words = CommandWords(park=("later",))
    assert parse_command("later notes", words) == Park("notes")
    assert parse_command("park notes", words) == Unknown("park")


@pytest.mark.parametrize(
    ("lists", "parked", "message"),
    [
        (Lists(), (), "started fix the build"),
        (
            DAY,
            (ParkedTask(ACTIVE, LeftOff()), WAITING, LEFT),
            f"started fix the build · parked {ACTIVE.title}",
        ),
    ],
)
def test_new_starts_a_task_and_parks_the_active_one(
    lists: Lists, parked: tuple[ParkedTask, ...], message: str
) -> None:
    result = applied(lists, "new fix the build")
    assert result.lists == Lists(Task("fix the build"), parked)
    assert result.events[-1] == Event(NOW, "started", "fix the build")
    assert result.message == message


@pytest.mark.parametrize(
    ("text", "reason", "event", "message"),
    [
        (
            "park retry loop",
            LeftOff("retry loop"),
            ("parked", "left off: retry loop"),
            f"parked {ACTIVE.title}",
        ),
        ("pause", LeftOff(), ("parked", ""), f"parked {ACTIVE.title}"),
        ("wait CI", Waiting("CI"), ("waiting", "on CI"), f"{ACTIVE.title} is waiting on CI"),
    ],
)
def test_park_and_wait_put_the_active_task_on_top_of_parked(
    text: str, reason: LeftOff | Waiting, event: tuple[str, str], message: str
) -> None:
    result = applied(DAY, text)
    assert result.lists == Lists(Idle(), (ParkedTask(ACTIVE, reason), WAITING, LEFT))
    assert [(e.kind, e.detail) for e in result.events] == [event]
    assert result.message == message


def test_done_finishes_the_active_task() -> None:
    result = applied(DAY, "done")
    assert result.lists == IDLE_DAY
    assert result.events == (Event(NOW, "finished", ACTIVE.title),)
    assert result.message == f"finished {ACTIVE.title}"


@pytest.mark.parametrize(
    ("lists", "text", "after", "message"),
    [
        (
            DAY,
            "s TIDY",
            Lists(LEFT.task, (ParkedTask(ACTIVE, LeftOff()), WAITING)),
            f"switched to {LEFT.task.title} · parked {ACTIVE.title} · left off: half done",
        ),
        (
            IDLE_DAY,
            "s 1129",
            Lists(WAITING.task, (LEFT,)),
            f"switched to {WAITING.task.title} · was waiting on review",
        ),
    ],
)
def test_switch_parks_the_active_task_and_says_where_i_was(
    lists: Lists, text: str, after: Lists, message: str
) -> None:
    result = applied(lists, text)
    assert result.lists == after
    assert result.events[-1].kind == "resumed"
    assert result.message == message


@pytest.mark.parametrize(
    ("lists", "query", "picked"),
    [
        (DAY, "1129", WAITING.task),  # a ticket number in a title
        (DAY, "2", LEFT.task),  # "1129" has a 2 in it, but not as a word: so position 2
        (
            Lists(Idle(), (LEFT, ParkedTask(Task("step 1 of the plan"), LeftOff()))),
            "1",
            Task("step 1 of the plan"),
        ),
    ],
)
def test_switch_matches_a_title_before_a_position(lists: Lists, query: str, picked: Task) -> None:
    assert applied(lists, f"s {query}").lists.active == picked


GOALS = ("fix the vulnerabilities", "migrate the build")
FOCUSED = Lists(ACTIVE, (WAITING, LEFT), GOALS)


def test_focus_adds_a_goal_while_a_slot_is_free() -> None:
    result = applied(Lists(), "focus fix the vulnerabilities")
    assert result.lists == Lists(focus=("fix the vulnerabilities",))
    assert result.events == (Event(NOW, "focused", "fix the vulnerabilities"),)
    assert result.message == "focusing on fix the vulnerabilities"


def test_unfocus_removes_one_by_its_number_on_the_card() -> None:
    result = applied(FOCUSED, "unfocus 2")
    assert result.lists.focus == ("fix the vulnerabilities",)
    assert result.events == (Event(NOW, "unfocused", "migrate the build"),)
    # A number is the row, even when another goal has it as a word: the removal is saved at once.
    assert applied(Lists(focus=("ship phase 2", "migrate")), "unfocus 2").lists.focus == (
        "ship phase 2",
    )


@pytest.mark.parametrize("text", ["new a", "park", "wait CI", "s 1129", "done"])
def test_focus_stays_put_whatever_happens_to_tasks(text: str) -> None:
    assert applied(FOCUSED, text).lists.focus == GOALS


TWINS = Lists(Idle(), (ParkedTask(Task("same"), LeftOff()), ParkedTask(Task("same"), LeftOff())))


@pytest.mark.parametrize(
    ("lists", "text", "reason"),
    [
        (Lists(), "park", "nothing is active"),
        (Lists(), "done", "nothing is active"),
        (DAY, "new", "new needs a title"),
        (DAY, "wait", "wait on what?"),
        (DAY, "switch", "switch to what?"),
        (DAY, "s nope", "no parked task matches 'nope'"),
        (DAY, "s ²", "no parked task matches '²'"),
        (DAY, f"s {'9' * 5000}", f"no parked task matches '{'9' * 5000}'"),
        (TWINS, "s same", "'same' matches 2: 1 same, 2 same"),
        (DAY, "done 1129", "done finishes the active task: type just done"),
        (DAY, "focus", "focus on what?"),
        (FOCUSED, "focus a third", "focus is full: unfocus one first, by number or name"),
        (FOCUSED, "focus Migrate the build", "already focusing on Migrate the build"),
        (FOCUSED, "unfocus", "unfocus which? its number or name"),
        (DAY, "hello", "not a command: hello"),
        (DAY, "", "type a command"),
    ],
)
def test_rejections_say_why_and_change_nothing(lists: Lists, text: str, reason: str) -> None:
    assert run(lists, text) == Rejected(reason)
