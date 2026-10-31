from dataclasses import replace
from datetime import date, datetime, timedelta, timezone

import pytest

from app.core import highlight
from app.core.commands import Applied, Ask, Preview, Rejected, apply, parse_command, preview
from app.core.listing import listing
from app.core.model import (
    CommandWords,
    FromQuick,
    Idle,
    LeftOff,
    Lists,
    NoStar,
    ParkedTask,
    Problem,
    Queued,
    Star,
    Task,
    Waiting,
)
from app.core.tasks_md import parse, render

NOW = datetime(2026, 10, 31, 9, 30, tzinfo=timezone(timedelta(hours=1)))
TODAY = NOW.date()
YESTERDAY = TODAY - timedelta(days=1)
WORDS = CommandWords()

ACTIVE = Task("1135 fix token refresh race")
WAITING = ParkedTask(Task("1129 password reset flow"), Waiting("review"))
LEFT = ParkedTask(Task("tidy logging config"), LeftOff("half done"))
DAY = Lists(ACTIVE, (WAITING, LEFT), quick=(Task("merge 1140", 3),))


def run(lists: Lists, text: str, now: datetime = NOW) -> Applied | Rejected:
    match parse_command(text, WORDS):
        case Ask():
            pytest.fail("for an agent")
        case command:
            return apply(lists, command, now)


def applied(lists: Lists, text: str, now: datetime = NOW) -> Applied:
    match run(lists, text, now):
        case Applied() as result:
            return result
        case Rejected(reason=reason):
            pytest.fail(f"rejected: {reason}")


def refused(lists: Lists, text: str) -> str:
    match run(lists, text):
        case Applied():
            pytest.fail("applied")
        case Rejected(reason=reason):
            return reason


def stars(lists: Lists) -> tuple[str, ...]:
    return tuple(task.title for task in highlight.starred(lists))


@pytest.mark.parametrize("line", ["new fix the build *", "+ fix the build *", "fix the build *"])
def test_a_star_at_the_end_of_a_new_task_makes_it_the_highlight_at_the_top(line: str) -> None:
    result = applied(DAY, line)
    top = result.lists.parked[0]
    assert top == ParkedTask(Task("fix the build", star=Star(TODAY)), Queued())
    assert result.lists.parked[1:] == DAY.parked
    assert result.message == (
        "added fix the build to the queue as p1 · ★ today's highlight · s p1 to start it"
    )
    assert [event.kind for event in result.events] == ["added", "starred"]


def test_a_star_comes_after_the_size() -> None:
    task = applied(DAY, "new fix the build ~1h *").lists.parked[0].task
    assert (task.title, task.minutes, task.star) == ("fix the build", 60, Star(TODAY))


@pytest.mark.parametrize("line", ["new ship it*", "new * ship it", "new ship * it"])
def test_a_star_that_is_not_the_last_word_on_its_own_stays_in_the_title(line: str) -> None:
    result = applied(DAY, line)
    assert result.lists.parked[-1].task.star == NoStar()
    assert result.lists.parked[-1].task.title == line.removeprefix("new ")


def test_a_star_alone_is_not_a_title() -> None:
    assert refused(DAY, "new *") == "a task needs a title"


def test_a_new_highlight_takes_the_star_off_the_old_one_and_says_so() -> None:
    first = applied(DAY, "new reply to Sam *").lists
    result = applied(first, "new fix the build *")
    assert stars(result.lists) == ("fix the build",)
    assert "★ today's highlight (was: reply to Sam)" in result.message
    assert [event.kind for event in result.events] == ["added", "unstarred", "starred"]


def test_starring_a_queued_task_moves_it_to_p1() -> None:
    result = applied(DAY, "star p2")
    assert result.lists.parked == (
        ParkedTask(replace(LEFT.task, star=Star(TODAY)), LeftOff("half done")),
        WAITING,
    )
    assert result.message == "★ tidy logging config is today's highlight, now p1"
    assert [event.kind for event in result.events] == ["starred"]


def test_starring_by_name_finds_the_task_as_switch_does() -> None:
    assert stars(applied(DAY, "star logging").lists) == ("tidy logging config",)
    assert stars(applied(DAY, "star 1129").lists) == ("1129 password reset flow",)
    assert stars(applied(DAY, "star 1135").lists) == (ACTIVE.title,)


def test_a_number_that_names_no_task_is_the_queues_row() -> None:
    assert stars(applied(DAY, "star 2").lists) == ("tidy logging config",)


def test_star_alone_stars_the_active_task_where_it_is() -> None:
    result = applied(DAY, "star")
    assert result.lists.active == replace(ACTIVE, star=Star(TODAY))
    assert result.lists.parked == DAY.parked
    assert result.message == f"★ {ACTIVE.title} is today's highlight"


def test_words_that_match_no_task_are_added_starred_at_the_top() -> None:
    result = applied(DAY, "star write the release notes ~30m")
    assert result.lists.parked[0].task == Task("write the release notes", 30, star=Star(TODAY))
    assert result.message.startswith("added write the release notes ~30m to the queue as p1 · ★")


@pytest.mark.parametrize("line", ["star q1", "star merge"])
def test_a_quick_item_cant_be_starred(line: str) -> None:
    assert refused(DAY, line) == highlight.NOT_QUICK


def test_a_task_from_quick_cant_be_starred() -> None:
    lists = replace(DAY, active=FromQuick(Task("merge 1129", 3)), quick=())
    assert refused(lists, "star") == highlight.NOT_QUICK


def test_refusals() -> None:
    assert refused(DAY, "star p9") == "there's no p9 in the queue"
    assert refused(replace(DAY, active=Idle()), "star").startswith("nothing is active")
    assert refused(DAY, "unstar") == "nothing is starred"
    assert refused(DAY, "unstar it").startswith("unstar takes the star off")
    assert "matches 2" in refused(DAY, "star i")


def test_starring_it_again_the_same_day_is_refused() -> None:
    starred = applied(DAY, "star").lists
    assert refused(starred, "star") == f"{ACTIVE.title} is already today's highlight"
    on_top = applied(DAY, "star p2").lists
    assert refused(on_top, "star p1") == "tidy logging config is already today's highlight"


def test_starring_an_earlier_days_highlight_again_fills_it_for_today() -> None:
    lists = replace(DAY, active=replace(ACTIVE, star=Star(YESTERDAY)))
    result = applied(lists, "star")
    assert result.lists.active == replace(ACTIVE, star=Star(TODAY))
    assert "was" not in result.message


def test_unstar_takes_it_off() -> None:
    result = applied(applied(DAY, "star p2").lists, "unstar")
    assert stars(result.lists) == ()
    assert result.message == "took the star off tidy logging config"


def test_the_star_goes_with_the_task_when_its_parked_and_started() -> None:
    parked = applied(applied(DAY, "star").lists, "park").lists
    assert parked.parked[0].task.star == Star(TODAY)
    started = applied(parked, "s p1").lists
    assert started.active == replace(ACTIVE, star=Star(TODAY))


@pytest.mark.parametrize(
    ("day", "said"),
    [
        (TODAY, "today's highlight done"),
        (YESTERDAY, "yesterday's highlight done"),
        (date(2026, 10, 28), "the highlight from 28 Oct done"),
    ],
)
def test_finishing_the_highlight_says_so(day: date, said: str) -> None:
    lists = replace(DAY, active=replace(ACTIVE, star=Star(day)))
    result = applied(lists, "done")
    assert result.message == f"finished {ACTIVE.title} · {said}"
    assert result.events[0].detail == said


def test_an_earlier_days_highlight_is_hollow_and_says_so_with_no_other_note() -> None:
    queued = ParkedTask(Task("fix the build", star=Star(YESTERDAY)), Queued())
    assert highlight.shine(queued.task, TODAY) == "earlier"
    assert highlight.shine(queued.task, YESTERDAY) == "today"
    assert highlight.note(queued, TODAY) == "yesterday's highlight"
    waiting = replace(queued, reason=Waiting("Sam"))
    assert highlight.note(waiting, TODAY) == "waiting on Sam"


def test_the_star_is_marked_as_its_typed() -> None:
    assert preview("new fix it *", WORDS, DAY, NOW) == Preview(
        ((0, 3), (11, 12)), "today's highlight"
    )
    assert preview("fix it *", WORDS, DAY, NOW) == Preview(((7, 8),), "today's highlight")
    assert preview("fix it*", WORDS, DAY, NOW) == Preview()
    assert preview("star p2", WORDS, DAY, NOW).note.startswith("★ tidy logging config")
    assert preview("star q1", WORDS, DAY, NOW).note == highlight.NOT_QUICK


def test_tasks_md_keeps_the_star_and_its_day() -> None:
    lists = applied(applied(DAY, "new fix the build ~1h *").lists, "s p1").lists
    text = render(lists)
    assert "- fix the build ~1h * 2026-10-31\n" in text
    assert parse(text) == lists


def test_a_star_on_a_queued_task_is_read_back() -> None:
    lists = applied(DAY, "new fix the build *").lists
    assert parse(render(lists)) == lists


@pytest.mark.parametrize(
    ("text", "problem"),
    [
        (
            "# Parked\n- a * 2026-10-31\n- b * 2026-10-30\n",
            Problem(3, "only one task can be the highlight"),
        ),
        ("# Parked\n- a * 2026-02-30\n", Problem(2, "2026-02-30 isn't a real date, for the star")),
        ("# Parked\n- ~5m * 2026-10-31\n", Problem(2, "a task needs a title")),
        (
            "# Active\n- a * 2026-10-31\n  home: quick\n",
            Problem(3, "a task from quick can't be the highlight"),
        ),
    ],
)
def test_tasks_md_refuses_a_star_it_cant_keep(text: str, problem: Problem) -> None:
    assert parse(text) == problem


def test_a_star_without_a_day_is_part_of_the_title() -> None:
    match parse("# Parked\n- ship it *\n\n# Quick\n- tidy * 2026-10-31\n"):
        case Lists(parked=(parked,), quick=(quick,)):
            assert parked.task == Task("ship it *")
            assert quick == Task("tidy * 2026-10-31")
        case other:
            pytest.fail(f"read as {other}")


def test_the_lists_show_the_star() -> None:
    lists = applied(applied(DAY, "star").lists, "new fix the build *").lists
    shown = listing(lists, TODAY)
    assert "  1  fix the build · ★ today's highlight · queued" in shown
    assert f"  {ACTIVE.title}\n" in shown
    stale = listing(lists, TODAY + timedelta(days=1))
    assert "  1  fix the build · ☆ yesterday's highlight · queued" in stale
