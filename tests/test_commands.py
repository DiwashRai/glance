from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from app.core.commands import (
    AddStep,
    Applied,
    Command,
    Done,
    Finish,
    Focus,
    New,
    Park,
    Quick,
    Rejected,
    Skip,
    Switch,
    Unfocus,
    Unknown,
    Wait,
    apply,
    parse_command,
)
from app.core.model import (
    CommandWords,
    Event,
    FromQuick,
    Idle,
    LeftOff,
    Lists,
    ParkedTask,
    Step,
    Task,
    Waiting,
)
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
        ("q merge 1129 ~3m", Quick("merge 1129 ~3m")),
        ("done q2", Done("q2")),
        ("step rerun CI", AddStep("rerun CI")),
        (">", Skip()),
        ("finish", Finish()),
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
        (DAY, "s nope", "no task matches 'nope'"),
        (DAY, "s ²", "no task matches '²'"),
        (
            DAY,
            f"s {'9' * 5000}",
            f"no parked task matches '{'9' * 5000}' (quick items: s q<number>)",
        ),
        (DAY, "s q0000001", "there's no q0000001 in quick"),
        (DAY, "quick ~5m", "quick what? for example: quick merge 1129 ~3m"),
        (TWINS, "s same", "'same' matches 2: 1 same, 2 same"),
        (DAY, "done 1129", "done ticks the current step; done q<number> ticks off a quick item"),
        (DAY, "done q1", "there's no q1 in quick"),
        (DAY, "s q1", "there's no q1 in quick"),
        (DAY, "quick", "quick what? for example: quick merge 1129 ~3m"),
        (DAY, "focus", "focus on what?"),
        (FOCUSED, "focus a third", "focus is full: unfocus one first, by number or name"),
        (FOCUSED, "focus Migrate the build", "already focusing on Migrate the build"),
        (FOCUSED, "unfocus", "unfocus which? its number or name"),
        (Lists(), "step a", "nothing is active"),
        (DAY, "step", "step what? for example: step rerun CI with trace"),
        (DAY, "skip", "no steps to skip · step <text> adds one"),
        (DAY, "skip it", "skip moves past the current step: type just skip"),
        (DAY, "finish now", "finish finishes the active task: type just finish"),
        (DAY, "hello", "not a command: hello"),
        (DAY, "", "type a command"),
    ],
)
def test_rejections_say_why_and_change_nothing(lists: Lists, text: str, reason: str) -> None:
    assert run(lists, text) == Rejected(reason)


MERGE = Task("merge 1129", 3)
REPLY = Task("reply to Sam")
QUICK_DAY = Lists(ACTIVE, (WAITING, LEFT), quick=(MERGE, REPLY))


def test_quick_adds_smallest_first_with_unsized_last() -> None:
    result = applied(QUICK_DAY, "quick review #415 ~1h")
    assert result.lists.quick == (MERGE, Task("review #415", 60), REPLY)
    assert result.events == (Event(NOW, "added", "review #415", "~1h"),)
    assert result.message == "added review #415 ~1h to quick"


def test_done_ticks_off_a_quick_item_without_making_it_active() -> None:
    result = applied(QUICK_DAY, "done q1")
    assert result.lists == replace(QUICK_DAY, quick=(REPLY,))
    assert result.events == (Event(NOW, "finished", "merge 1129"),)


def test_a_quick_item_switched_to_goes_back_to_quick_unless_it_gains_a_note() -> None:
    picked = applied(QUICK_DAY, "s q2")
    assert picked.lists.active == FromQuick(REPLY)
    assert picked.lists.quick == (MERGE,)
    back = applied(picked.lists, "park")
    assert back.lists.quick == (MERGE, REPLY)
    assert back.message == "put reply to Sam back in quick"
    noted = applied(picked.lists, "wait Sam's answer")
    assert noted.lists.parked[0] == ParkedTask(Task("reply to Sam"), Waiting("Sam's answer"))
    assert applied(picked.lists, "new x").message == "started x · put reply to Sam back in quick"


ROADMAP = Task("review Q2 roadmap", 3)


@pytest.mark.parametrize(
    ("lists", "text", "active"),
    [
        # q2 is always Quick row 2, even when another title has "q2" in it
        (Lists(quick=(ROADMAP, REPLY)), "s q2", FromQuick(REPLY)),
        (
            Lists(parked=(ParkedTask(ROADMAP, LeftOff()),), quick=(MERGE, REPLY)),
            "s Q2",
            FromQuick(REPLY),
        ),
        # a number only looks at Parked, whose rows are numbered
        (Lists(parked=(LEFT, WAITING), quick=(Task("merge 2"),)), "s 2", WAITING.task),
    ],
)
def test_switch_picks_the_row_the_card_shows(
    lists: Lists, text: str, active: Task | FromQuick
) -> None:
    assert applied(lists, text).lists.active == active


def test_done_q2_ticks_row_2_even_when_another_title_says_q2() -> None:
    assert applied(Lists(quick=(ROADMAP, REPLY)), "done q2").lists.quick == (ROADMAP,)


def said(lists: Lists, *texts: str) -> tuple[Lists, list[str]]:
    """Runs each line in turn, keeping what glance said."""
    messages: list[str] = []
    for text in texts:
        result = applied(lists, text)
        lists = result.lists
        messages.append(result.message)
    return lists, messages


def test_done_ticks_steps_in_order_and_the_last_takes_a_second_done() -> None:
    lists, messages = said(DAY, "step reproduce it", "step rerun CI", "done", "done", "done")
    assert messages[2:] == [
        "done: reproduce it · next: rerun CI · 2/2",
        "done: rerun CI · all 2 steps done · done again to finish 1135 fix token refresh race",
        "finished 1135 fix token refresh race",
    ]
    assert lists.active == Idle()


def test_skipped_steps_come_back_round_then_done_finishes_anyway() -> None:
    lists, messages = said(DAY, "step a", "step b", "skip", "done", "skip")
    assert messages[2:] == [
        "skipped: a · next: b · 2/2",
        "done: b · back to skipped: a",
        "skipped again: a · only skipped steps left · done to finish anyway",
    ]
    reason = "nothing to skip · only skipped steps left · done to finish anyway"
    assert run(lists, "skip") == Rejected(reason)
    finished = applied(lists, "done").message
    assert finished == "finished 1135 fix token refresh race · 1 step skipped"


def test_finish_finishes_early_and_says_what_was_left() -> None:
    _, messages = said(DAY, "step a", "step b", "finish")
    assert messages[-1] == "finished 1135 fix token refresh race · 2 steps not done"


def test_a_quick_item_given_steps_is_a_real_task_and_parks_in_parked() -> None:
    lists, messages = said(QUICK_DAY, "s q2", "step find the notes", "park")
    assert messages[1] == "added step 1: find the notes · it's a task now, not a quick item"
    assert lists.quick == (MERGE,)
    assert lists.parked[0].task == Task("reply to Sam", steps=(Step("find the notes"),))


def test_one_step_reads_well_and_skip_after_it_says_whats_next() -> None:
    lists, messages = said(DAY, "step a", "done")
    finish_line = "the step is done · done again to finish 1135 fix token refresh race"
    assert messages[1] == f"done: a · {finish_line}"
    assert run(lists, "skip") == Rejected(f"nothing to skip · {finish_line}")


def test_parking_and_coming_back_keeps_the_steps_and_the_place() -> None:
    lists, messages = said(DAY, "step a", "step b", "done", "park", "new x", "s 1")
    assert lists.active == replace(ACTIVE, steps=(Step("a", "done"), Step("b")))
    assert messages[-1].endswith(" · on b · 2/2")
    _, messages = said(lists, "done", "park", "s 1")
    assert messages[-1].endswith(" · all 2 steps done")
