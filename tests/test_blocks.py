from datetime import date, datetime, time, timedelta, timezone

import pytest

from app.core.commands import Applied, Rejected, apply, parse_command
from app.core.model import Block, CommandWords, Event, Lists, Plan
from app.core.tasks_md import Problem, parse, render

NOW = datetime(2026, 10, 18, 9, 58, 40, tzinfo=timezone(timedelta(hours=1)))
TODAY = NOW.date()
DEEP = Block(time(14), time(15, 30), "deep work")
RUN = Block(time(17, 30), time(18, 30), "run", must=True)
PLANNED = Lists(plan=Plan(TODAY, (DEEP, RUN)))


def run(lists: Lists, text: str) -> Applied | Rejected:
    return apply(lists, parse_command(text, CommandWords()), NOW)


def applied(lists: Lists, text: str) -> Applied:
    match run(lists, text):
        case Applied() as result:
            return result
        case Rejected(reason=reason):
            pytest.fail(f"rejected: {reason}")


def test_block_adds_to_todays_plan_in_time_order_by_end_or_length() -> None:
    result = applied(Lists(plan=Plan(TODAY, (RUN,))), "block 14:00-15:30 deep work")
    assert result.lists.plan == Plan(TODAY, (DEEP, RUN))
    assert result.events == (Event(NOW, "planned", "deep work", "14:00-15:30"),)
    assert result.message == "planned deep work 14:00-15:30"
    assert applied(Lists(), "block 17:30 1h run !").message == (
        "planned run 17:30-18:30 · must happen today"
    )
    assert applied(Lists(), "block 9:05 1h30m ship it!").lists.plan == Plan(
        TODAY, (Block(time(9, 5), time(10, 35), "ship it!"),)
    )


def test_a_block_on_a_stale_plan_starts_todays() -> None:
    stale = Lists(plan=Plan(date(2026, 10, 17), (DEEP,)))
    assert applied(stale, "block 14:30 1h review").lists.plan == Plan(
        TODAY, (Block(time(14, 30), time(15, 30), "review"),)
    )
    assert applied(stale, "block 9:00 1h x").message.endswith("replaces the plan for 2026-10-17")
    assert run(stale, "unblock 1") == Rejected("nothing is planned today")


@pytest.mark.parametrize(
    ("text", "reason"),
    [
        ("block", "block when? 14:00 1h deep work, or 14:00-15:30 PR reviews"),
        ("block deep work", "a block starts with its time"),
        ("block 14:00 deep work", "how long? an end or a length"),
        ("block 14:00 1h", "what's the block for?"),
        ("block 15:00-14:00 x", "a block ends after it starts, before midnight"),
        ("block 23:30 1h x", "a block ends before midnight: 23:59 at the latest"),
        # saved as 14:00-15:00 30m review, it would read back as an end and a length
        ("block 14:00 1h 30m review", "the name can't start with a length"),
        ("block 15:00 1h review", "that overlaps 14:00-15:30 deep work"),
    ],
)
def test_block_refuses_what_it_cant_plan(text: str, reason: str) -> None:
    match run(PLANNED, text):
        case Rejected(reason=said):
            assert said.startswith(reason)
        case Applied():
            pytest.fail("expected a refusal")


def test_unblock_by_number_in_time_order_or_by_name() -> None:
    result = applied(PLANNED, "unblock 2")
    assert result.lists.plan == Plan(TODAY, (DEEP,))
    assert result.events == (Event(NOW, "unplanned", "run", "17:30-18:30"),)
    assert result.message == "unblocked run 17:30-18:30 · must happen today"
    assert applied(PLANNED, "unblock deep").lists.plan == Plan(TODAY, (RUN,))
    assert run(PLANNED, "unblock 3") == Rejected("no block today matches '3'")


def test_todays_plan_round_trips_in_tasks_md() -> None:
    text = (
        "# Active\n\n# Focus\n\n# Parked\n\n# Quick\n\n"
        "# Today 2026-10-18\n- 14:00-15:30 deep work\n- 17:30-18:30 run !\n"
    )
    assert parse(text) == PLANNED
    assert render(PLANNED) == text
    # By hand: any order, a length instead of an end, any spaces or tabs
    hand = "# Today 2026-10-18\n- 17:30  1h\trun !\n- 14:00-15:30\tdeep work\n"
    assert parse(hand) == PLANNED


@pytest.mark.parametrize(
    ("text", "line", "message"),
    [
        ("# Today\n", 1, "the date goes after Today, like '# Today 2026-10-18'"),
        ("# Today 2026-02-30\n", 1, "2026-02-30 isn't a real date"),
        ("# Today 2026-10-18\n# Today 2026-10-18\n", 2, "'# Today' appears twice"),
        ("# Today 2026-10-18\n- deep work\n", 2, "a block starts with its time"),
        ("# Today 2026-10-18\n- 14:00-15:00 a\n- 14:30 1h b\n", 3, "that overlaps 14:00-15:00 a"),
        ("# Today 2026-10-18\n- 14:00 1h a\n  left off: x\n", 3, "a block can't have a note"),
    ],
)
def test_tasks_md_refuses_a_plan_it_cant_read(text: str, line: int, message: str) -> None:
    match parse(text):
        case Problem() as problem:
            assert problem.line == line
            assert problem.message.startswith(message)
        case Lists() as lists:
            pytest.fail(f"expected a problem, got {lists}")
