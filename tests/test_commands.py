from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from app.core.commands import (
    AddStep,
    Applied,
    Ask,
    Command,
    Done,
    Finish,
    Focus,
    New,
    Park,
    Preview,
    Quick,
    Rejected,
    Remove,
    Skip,
    Star,
    Switch,
    Typed,
    Unfocus,
    Unstar,
    apply,
    parse_command,
    preview,
    spaces_for,
)
from app.core.model import (
    CommandWords,
    Event,
    FromQuick,
    Idle,
    LeftOff,
    Lists,
    ParkedTask,
    Queued,
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
    match parse_command(text, WORDS):
        case Ask():
            pytest.fail("for the assistant")
        case command:
            return apply(lists, command, NOW)


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
        ("PAUSE retry loop", Park(LeftOff("retry loop"))),
        ("shelve", Park(LeftOff())),
        ("wait CI run", Park(Waiting("CI run"))),
        ("s 1129", Switch("1129")),
        ("d", Done()),
        ("done 1129", Done("1129")),
        ("new\tfix  the   build ", New("fix the build")),
        ("Focus fix the vulnerabilities", Focus("fix the vulnerabilities")),
        ("unfocus 2", Unfocus("2")),
        ("q merge 1129 ~3m", Quick("merge 1129 ~3m")),
        ("done q2", Done("q2")),
        ("RM p2", Remove("p2")),
        ("step rerun CI", AddStep("rerun CI")),
        (">", Skip()),
        ("finish", Finish()),
        ("star", Star()),
        ("STAR p3", Star("p3")),
        ("unstar", Unstar()),
        ("hello there", Typed("hello there")),
        (" what's next?", Ask("assistant", "what's next?")),
        ("  ask backend", Ask("chief", "ask backend")),
        ("     ask backend", Ask("chief", "ask backend")),
    ],
)
def test_parses_the_first_word(text: str, command: Command | Ask) -> None:
    assert parse_command(text, WORDS) == command


@pytest.mark.parametrize("text", ["new a\n- b", f"new a{chr(0x2028)}- b"])
def test_line_breaks_become_one_space_so_tasks_md_reads_back(text: str) -> None:
    result = applied(Lists(), text)
    assert result.lists.parked == (ParkedTask(Task("a - b"), Queued()),)
    assert parse(render(result.lists)) == result.lists


def test_words_come_from_settings() -> None:
    words = CommandWords(park=("later",))
    assert parse_command("later notes", words) == Park(LeftOff("notes"))
    assert parse_command("park notes", words) == Typed("park notes")
    # with one agent, any number of spaces is for it
    assert parse_command("  x", CommandWords(agents=("me",))) == Ask("me", "x")


def test_a_reply_offered_with_spaces_goes_to_that_agent() -> None:
    """The message card shows how many spaces answer its sender."""
    for agent in WORDS.agents:
        assert parse_command(" " * spaces_for(agent, WORDS) + "yes", WORDS) == Ask(agent, "yes")
    assert spaces_for("backup-script", WORDS) == 0  # not an agent: no reply offered


NEW = ParkedTask(Task("fix the build"), Queued())


@pytest.mark.parametrize(
    ("lists", "message"),
    [
        (Lists(), "added fix the build to the queue as p1 · s p1 to start it"),
        (DAY, "added fix the build to the queue as p3 · s p3 to start it"),
        (IDLE_DAY, "added fix the build to the queue as p3 · s p3 to start it"),
    ],
)
def test_new_goes_to_the_bottom_of_the_queue_and_leaves_active_alone(
    lists: Lists, message: str
) -> None:
    result = applied(lists, "new fix the build")
    assert result.lists == replace(lists, parked=(*lists.parked, NEW))
    assert applied(lists, "fix  the build").lists == result.lists  # no command word: new
    assert result.events == (Event(NOW, "added", "fix the build", "to the queue"),)
    assert result.message == message
    assert parse(render(result.lists)) == result.lists  # still queued once saved


def test_a_queued_task_starts_by_its_row_and_comes_back_on_top_once_parked() -> None:
    queued = applied(DAY, "new fix the build").lists
    started = applied(queued, "s p3")
    assert started.lists == Lists(NEW.task, (ParkedTask(ACTIVE, LeftOff()), WAITING, LEFT))
    assert started.message == f"switched to fix the build · parked {ACTIVE.title}"
    assert applied(started.lists, "park").lists.parked[0] == ParkedTask(NEW.task, LeftOff())


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
        (DAY, "new", "a task needs a title"),
        (DAY, "~5m", "a task needs a title"),
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
        (DAY, "s p3", "there's no p3 in the queue"),
        (DAY, "s P0", "there's no p0 in the queue"),
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
        (DAY, "rm 1129", "rm f1, p1 or q1"),
        (DAY, "rm p3", "there's no p3 in parked"),
        (DAY, "rm q1", "there's no q1 in quick"),
        (DAY, "rm f1", "no focus matches '1'"),
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
    assert result.events == (Event(NOW, "crossed", "merge 1129"),)


@pytest.mark.parametrize(
    ("text", "left", "event", "said"),
    [
        ("rm p2", replace(QUICK_DAY, parked=(WAITING,)), "tidy logging config", "parked"),
        ("rm Q1", replace(QUICK_DAY, quick=(REPLY,)), "merge 1129", "quick"),
    ],
)
def test_rm_takes_a_row_off_its_card_and_leaves_the_rest(
    text: str, left: Lists, event: str, said: str
) -> None:
    result = applied(QUICK_DAY, text)
    assert result.lists == left
    assert result.events == (Event(NOW, "removed", event, f"from {said}"),)
    assert result.message.startswith(f"removed {event}")
    assert applied(FOCUSED, "rm f2").lists.focus == GOALS[:1]  # as unfocus 2 does


@pytest.mark.parametrize(
    ("text", "note"),
    [("rm p2", "removes tidy logging config"), ("rm q9", "there's no q9 in quick")],
)
def test_rm_says_what_it_would_remove_before_enter(text: str, note: str) -> None:
    """It can't be undone, and the cards number Parked 1, 2…, not p1, p2…"""
    assert preview(text, WORDS, QUICK_DAY, NOW) == Preview(((0, 2),), note)


def test_a_quick_item_switched_to_goes_back_to_quick_unless_it_gains_a_note() -> None:
    picked = applied(QUICK_DAY, "s q2")
    assert picked.lists.active == FromQuick(REPLY)
    assert picked.lists.quick == (MERGE,)
    back = applied(picked.lists, "park")
    assert back.lists.quick == (MERGE, REPLY)
    assert back.message == "put reply to Sam back in quick"
    noted = applied(picked.lists, "wait Sam's answer")
    assert noted.lists.parked[0] == ParkedTask(Task("reply to Sam"), Waiting("Sam's answer"))
    assert applied(picked.lists, "new x").lists.active == FromQuick(REPLY)  # new leaves it


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
        # p2 is always Parked row 2, even when another title has "p2" in it
        (Lists(parked=(ParkedTask(Task("ship p2"), LeftOff()), LEFT)), "s p2", LEFT.task),
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


STARRED_FIX = Task("fix the build", starred=True)
OTHER = ParkedTask(Task("tidy logging config"), LeftOff("half done"))
HELD = ParkedTask(Task("1129 reset flow", starred=True), Waiting("review"))
UNHELD = ParkedTask(Task("1129 reset flow"), Waiting("review"))


def starred_titles(lists: Lists) -> list[str]:
    match lists.active:
        case Task(starred=True, title=title):
            active = [title]
        case _:
            active = []
    return [*active, *(item.task.title for item in lists.parked if item.task.starred)]


@pytest.mark.parametrize(
    "text",
    ["new fix the build *", "fix the build *", "+ fix the build  * ", "new fix the build * *"],
)
def test_a_lone_star_at_the_end_adds_a_starred_task_at_p1(text: str) -> None:
    result = applied(Lists(Idle(), (OTHER,)), text)
    assert result.lists.parked == (ParkedTask(STARRED_FIX, Queued()), OTHER)
    assert result.events == (
        Event(NOW, "added", "fix the build", "to the queue"),
        Event(NOW, "starred", "fix the build"),
    )
    assert result.message == "added fix the build to the queue as p1, starred · s p1 to start it"
    assert parse(render(result.lists)) == result.lists


def test_a_size_goes_before_the_star() -> None:
    assert applied(Lists(), "fix the build ~1h *").lists.parked[0].task == replace(
        STARRED_FIX, minutes=60
    )


def test_a_star_that_isnt_the_last_word_stays_in_the_title() -> None:
    assert applied(Lists(), "new fix * now").lists.parked[0].task == Task("fix * now")
    assert applied(Lists(), "new fix*").lists.parked[0].task == Task("fix*")
    sized_task = applied(Lists(), "new fix * ~1h").lists
    assert sized_task.parked[0].task == Task("fix *", 60)
    assert parse(render(sized_task)) == sized_task


@pytest.mark.parametrize("text", ["new *", "*", "* *", "new ~1h *", "star ~1h"])
def test_a_star_alone_is_no_title(text: str) -> None:
    assert run(Lists(), text) == Rejected("a task needs a title")


def test_a_block_line_with_a_star_after_it_is_a_task() -> None:
    assert applied(Lists(), "call 2pm for 1h *").lists.parked[0].task == Task(
        "call 2pm for 1h", starred=True
    )


@pytest.mark.parametrize(
    ("text", "parked"),
    [
        ("star p2", (replace(OTHER, task=replace(OTHER.task, starred=True)), UNHELD)),
        ("star P2", (replace(OTHER, task=replace(OTHER.task, starred=True)), UNHELD)),
        ("star 2", (replace(OTHER, task=replace(OTHER.task, starred=True)), UNHELD)),
        ("star tidy", (replace(OTHER, task=replace(OTHER.task, starred=True)), UNHELD)),
        ("star tidy *", (replace(OTHER, task=replace(OTHER.task, starred=True)), UNHELD)),
    ],
)
def test_starring_moves_the_star_and_the_task_to_p1(
    text: str, parked: tuple[ParkedTask, ...]
) -> None:
    result = applied(Lists(ACTIVE, (HELD, OTHER)), text)
    assert result.lists == Lists(ACTIVE, parked)
    assert result.events == (
        Event(NOW, "unstarred", "1129 reset flow"),
        Event(NOW, "starred", "tidy logging config"),
    )
    assert result.message == (
        "starred tidy logging config as p1 · took the star off 1129 reset flow"
    )
    assert parse(render(result.lists)) == result.lists


def test_star_alone_stars_the_active_task_and_it_stays_active() -> None:
    result = applied(Lists(ACTIVE, (HELD,)), "star")
    assert result.lists == Lists(replace(ACTIVE, starred=True), (UNHELD,))
    assert result.message == (
        "starred 1135 fix token refresh race · took the star off 1129 reset flow"
    )
    assert applied(Lists(ACTIVE), "star 1135").lists.active == replace(ACTIVE, starred=True)
    assert applied(Lists(ACTIVE), "star *").lists.active == replace(ACTIVE, starred=True)


def test_starring_takes_the_star_off_the_active_task() -> None:
    lists = Lists(STARRED_FIX, (OTHER,))
    result = applied(lists, "star p1")
    assert result.lists.active == Task("fix the build")
    assert starred_titles(result.lists) == ["tidy logging config"]


def test_starring_the_starred_task_again_keeps_it_and_doesnt_say_it_lost_it() -> None:
    down = Lists(Idle(), (OTHER, HELD))
    result = applied(down, "star p2")
    assert result.lists.parked == (HELD, OTHER)
    assert result.message == "starred 1129 reset flow as p1"
    assert applied(Lists(STARRED_FIX), "star").message == "starred fix the build"


def test_star_words_that_match_nothing_add_a_starred_task_and_say_so() -> None:
    result = applied(Lists(ACTIVE, (HELD,)), "star ship the thing ~1h")
    assert result.lists == Lists(
        ACTIVE, (ParkedTask(Task("ship the thing", 60, starred=True), Queued()), UNHELD)
    )
    assert result.message == (
        "added ship the thing ~1h to the queue as p1, starred · "
        "took the star off 1129 reset flow · s p1 to start it"
    )


@pytest.mark.parametrize(
    ("lists", "text", "reason"),
    [
        (Lists(quick=(MERGE,)), "star q1", "quick items can't be starred"),
        (Lists(quick=(MERGE,)), "star q9", "quick items can't be starred"),
        (Lists(quick=(MERGE,)), "star merge", "quick items can't be starred"),
        (Lists(FromQuick(MERGE)), "star", "quick items can't be starred"),
        (Lists(FromQuick(MERGE)), "star merge", "quick items can't be starred"),
        (Lists(), "star", "nothing is active"),
        (Lists(parked=(OTHER,)), "star p9", "there's no p9 in the queue"),
        (Lists(parked=(OTHER,)), "star 9", "there's no p9 in the queue"),
        (Lists(), "unstar", "nothing is starred"),
        (Lists(STARRED_FIX), "unstar now", "unstar takes the star off: type just unstar"),
    ],
)
def test_star_refuses(lists: Lists, text: str, reason: str) -> None:
    assert run(lists, text) == Rejected(reason)


def test_a_number_in_a_title_wins_over_a_row_as_in_switch() -> None:
    lists = Lists(Idle(), (OTHER, ParkedTask(Task("ticket 1"), Queued())))
    assert applied(lists, "star 1").lists.parked[0].task == Task("ticket 1", starred=True)


def test_star_matching_several_lists_them_across_active_parked_and_quick() -> None:
    lists = Lists(Task("fix a"), (ParkedTask(Task("fix b"), Queued()),), quick=(Task("fix c"),))
    assert run(lists, "star fix") == Rejected("'fix' matches 3: p1 fix b, active fix a, q1 fix c")


def test_a_number_never_looks_at_quick_and_never_adds_a_task() -> None:
    lists = Lists(Idle(), (OTHER, UNHELD), quick=(Task("merge 2"),))
    assert applied(lists, "star 2").lists.parked[0].task == replace(UNHELD.task, starred=True)
    assert run(lists, "star 3") == Rejected("there's no p3 in the queue")
    assert run(Lists(quick=(Task("merge 2"),)), "star 2") == Rejected("there's no p2 in the queue")


def test_unstar_takes_it_off_wherever_it_is() -> None:
    result = applied(Lists(Idle(), (HELD,)), "unstar")
    assert result.lists == Lists(Idle(), (UNHELD,))
    assert result.events == (Event(NOW, "unstarred", "1129 reset flow"),)
    assert result.message == "took the star off 1129 reset flow"
    assert applied(Lists(STARRED_FIX), "unstar").lists.active == Task("fix the build")


def test_the_star_stays_with_the_task_through_parking_steps_and_switching() -> None:
    lists, _ = said(Lists(STARRED_FIX, (OTHER,)), "step a", "done", "park", "s 2", "s 1")
    assert lists.active == Task("fix the build", steps=(Step("a", "done"),), starred=True)
    assert starred_titles(lists) == ["fix the build"]
    assert parse(render(lists)) == lists


@pytest.mark.parametrize("text", ["done", "finish"])
def test_finishing_takes_the_star_with_it(text: str) -> None:
    assert starred_titles(applied(Lists(STARRED_FIX), text).lists) == []


def test_removing_takes_the_star_with_it() -> None:
    assert starred_titles(applied(Lists(Idle(), (HELD,)), "rm p1").lists) == []


@pytest.mark.parametrize("text", ["quick tidy *", "q tidy * *"])
def test_a_quick_item_never_comes_back_starred(text: str) -> None:
    added = applied(Lists(), text)
    assert added.lists.quick == (Task("tidy"),)
    assert added.message == "added tidy to quick · quick items can't be starred"
    parked = applied(applied(added.lists, "s q1").lists, "park half done").lists
    assert parked.parked == (ParkedTask(Task("tidy"), LeftOff("half done")),)
    assert parse(render(parked)) == parked


def test_unstar_leaves_no_star_to_read_back() -> None:
    lists = applied(applied(Lists(), "new foo * *").lists, "unstar").lists
    assert lists.parked[0].task == Task("foo")
    assert parse(render(lists)) == lists


def test_a_quick_item_with_a_star_and_nothing_else_has_no_title() -> None:
    assert run(Lists(), "quick *") == Rejected("quick what? for example: quick merge 1129 ~3m")


@pytest.mark.parametrize(
    ("text", "marks"),
    [
        ("fix it *", ((7, 8),)),
        ("fix it * ", ((7, 8),)),
        ("fix it * *", ((7, 8), (9, 10))),
        ("fix * it", ()),
        ("new fix it *", ((0, 3), (11, 12))),
        ("star fix", ((0, 4),)),
        ("star fix *", ((0, 4), (9, 10))),
        ("quick tidy *", ((0, 5),)),
    ],
)
def test_the_star_is_marked_as_its_typed(text: str, marks: tuple[tuple[int, int], ...]) -> None:
    assert preview(text, WORDS, Lists(), NOW) == Preview(marks)
