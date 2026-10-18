from dataclasses import replace
from datetime import date, datetime, time, timedelta, timezone

import pytest

from app.core.blocks import planned
from app.core.commands import Applied, Ask, Preview, Rejected, apply, parse_command, preview
from app.core.model import Block, CommandWords, Event, Lists, NoPlan, Plan, Task
from app.core.tasks_md import Problem, parse, render

NOW = datetime(2026, 10, 18, 9, 58, 40, tzinfo=timezone(timedelta(hours=1)))
TODAY = NOW.date()
DEEP = Block(time(14), time(15, 30), "deep work")
RUN = Block(time(17, 30), time(18, 30), "run", must=True)
PLANNED = Lists(plan=Plan(TODAY, (DEEP, RUN)))


def run(lists: Lists, text: str) -> Applied | Rejected:
    match parse_command(text, CommandWords()):
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
    ("text", "block"),
    [
        ("deep work 2pm for 1h30m", DEEP),
        ("deep work for 90m 2pm", DEEP),  # either order
        ("standup 10 for 15m", Block(time(10), time(10, 15), "standup")),  # the next 10
        ("standup 9 for 15m", Block(time(21), time(21, 15), "standup")),  # 9:00 has gone
        ("review 9am for 30m", Block(time(9), time(9, 30), "review")),  # gone, but it said am
        ("lunch 12 for 1h", Block(time(12), time(13), "lunch")),
        ("early 09:00 for 30m", Block(time(9), time(9, 30), "early")),
        ("gym 18:30 for 1h", Block(time(18, 30), time(19, 30), "gym")),
        ("lunch noon for 1h", Block(time(12), time(13), "lunch")),  # a time looked up by name
        ("run 5:30PM for 1h !", RUN),
        # a name can't end in a lone !: tasks.md would read it as must
        ("run !! 5:30pm for 1h", RUN),
        ("ship it! 4pm for 1h", Block(time(16), time(17), "ship it!")),
        # it reads back from tasks.md as a name, not a length
        ("30m review 2pm for 1h", Block(time(14), time(15), "30m review")),
    ],
)
def test_a_line_ending_in_a_time_and_a_length_is_a_block(text: str, block: Block) -> None:
    result = applied(Lists(), text)
    assert result.lists.plan == Plan(TODAY, (block,))
    assert parse(render(result.lists)) == result.lists


def test_a_block_is_planned_not_started() -> None:
    result = applied(Lists(plan=Plan(TODAY, (RUN,))), "deep work 2pm for 90m")
    assert result.lists.plan == Plan(TODAY, (DEEP, RUN))
    assert result.events == (Event(NOW, "planned", "deep work", "14:00-15:30"),)
    assert result.message == "planned deep work 14:00-15:30"
    assert applied(Lists(), "run 5:30pm for 1h !").message == (
        "planned run 17:30-18:30 · must happen today"
    )


# Anything that doesn't end exactly like a block is a task: nothing turns blue, which says so
@pytest.mark.parametrize(
    "text", ["call dentist 3pm", "lunch for 1h", "deep work 2pm for 1.5h", "x 25pm for 1h"]
)
def test_without_a_time_and_a_length_its_a_task(text: str) -> None:
    assert applied(Lists(), text).lists == Lists(Task(text))


def deep(start: time, end: time) -> Block:
    return Block(start, end, "deep work")


@pytest.mark.parametrize(
    ("text", "left", "said"),
    [
        (
            "call 2:30pm for 30m",
            (deep(time(14), time(14, 30)), deep(time(15), time(15, 30))),
            "deep work now 14:00-14:30 and 15:00-15:30",
        ),
        ("call 3pm for 1h", (deep(time(14), time(15)),), "deep work now 14:00-15:00"),
        ("call 1pm for 1h30m", (deep(time(14, 30), time(15, 30)),), "deep work now 14:30-15:30"),
        ("planning 1:30pm for 3h", (), "removed deep work 14:00-15:30"),
        # the same name is cut back like any other: blocks are never merged or moved
        ("Deep work 2pm for 1h", (deep(time(15), time(15, 30)),), "deep work now 15:00-15:30"),
    ],
)
def test_a_newer_block_cuts_back_the_ones_it_lands_on(
    text: str, left: tuple[Block, ...], said: str
) -> None:
    result = applied(Lists(plan=Plan(TODAY, (DEEP,))), text)
    assert tuple(b for b in planned(result.lists.plan, TODAY) if b.what == "deep work") == left
    assert result.message.endswith(f" · {said}")


def test_a_block_split_in_two_is_unblocked_by_number() -> None:
    split = applied(PLANNED, "call 2:30pm for 30m").lists
    assert run(split, "unblock deep") == Rejected(
        "'deep' matches 2: 1 deep work 14:00-14:30, 3 deep work 15:00-15:30"
    )
    call = Block(time(14, 30), time(15), "call")
    assert planned(applied(split, "unblock 3").lists.plan, TODAY)[1:] == (call, RUN)


def test_a_block_on_a_stale_plan_starts_todays() -> None:
    stale = Lists(plan=Plan(date(2026, 10, 17), (DEEP,)))
    result = applied(stale, "review 2:30pm for 1h")
    assert result.lists.plan == Plan(TODAY, (Block(time(14, 30), time(15, 30), "review"),))
    assert result.message.endswith("replaces the plan for 2026-10-17")
    assert run(stale, "unblock 1") == Rejected("nothing is planned today")


@pytest.mark.parametrize(
    ("text", "reason"),
    [
        ("! 2pm for 1h", "what's the block for?"),
        ("x 9 for 3h", "from 21:00, that runs past midnight"),
        ("call 6pm for 1h", "run must happen: unblock it first"),
    ],
)
def test_a_block_glance_cant_plan_is_refused(text: str, reason: str) -> None:
    match run(PLANNED, text):
        case Rejected(reason=said):
            assert said.startswith(reason)
        case Applied():
            pytest.fail("expected a refusal")


@pytest.mark.parametrize(
    ("text", "shown"),
    [
        ("deep work 8am for 1h !", Preview(((10, 13), (14, 17), (18, 20), (21, 22)))),
        ("call for 30m 2:30pm", Preview(((5, 8), (9, 12), (13, 19)), "trims deep work")),
        ("plan 1pm for 3h", Preview(((5, 8), (9, 12), (13, 15)), "replaces deep work")),
        (
            "call 6pm for 1h",
            Preview(((5, 8), (9, 12), (13, 15)), "run must happen: unblock it first"),
        ),
        ("call dentist 3pm", Preview()),
        ("wait for Sam 3pm for 1h", Preview(((0, 4),))),  # the command word wins
        (" what's next?", Preview(agent="assistant", note="assistant")),
    ],
)
def test_preview_marks_what_glance_picked_up(text: str, shown: Preview) -> None:
    assert replace(preview(text, CommandWords(), PLANNED, NOW), plan=NoPlan()) == shown


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
        # by hand, an overlap is a mistake: it isn't cut back like a typed block
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
