from datetime import datetime, timedelta, timezone

import pytest

from app.core import events_log
from app.core.events_log import History
from app.core.model import Event, Idle
from app.core.tasks_md import Problem
from app.core.today import Day, Span, day, duration_text, total, worked

ZONE = timezone(timedelta(hours=1))


def at(hhmm: str) -> datetime:
    hour, minute = map(int, hhmm.split(":"))
    return datetime(2026, 10, 18, hour, minute, tzinfo=ZONE)


def test_each_start_runs_until_that_task_stops_and_the_last_runs_until_now() -> None:
    events = [
        Event(at("09:00"), "started", "1135"),
        Event(at("09:10"), "added", "1135", "~3m"),
        Event(at("09:12"), "crossed", "1135"),  # `done q1` on a namesake: 1135 carries on
        Event(at("09:12"), "ticked", "1135", "reproduce it"),
        Event(at("09:30"), "parked", "1135", "left off: retry loop"),
        Event(at("09:30"), "started", "review #415"),
        Event(at("09:45"), "finished", "review #415"),
        Event(at("10:00"), "resumed", "1135"),
    ]
    done = (Span("1135", at("09:00"), at("09:30")), Span("review #415", at("09:30"), at("09:45")))
    assert worked(events, at("10:20"), "1135") == (
        *done,
        Span("1135", at("10:00"), at("10:20"), going=True),
    )
    assert worked(events, at("10:20"), "") == done  # tasks.md emptied by hand: not still going


def test_time_on_tasks_counts_only_what_is_after_since() -> None:
    late = Span("late", at("00:00") - timedelta(hours=1), at("00:30"))
    spans = (late, Span("b", at("09:00"), at("09:45")))
    assert total(spans, at("00:00")) == timedelta(minutes=75)


@pytest.mark.parametrize(("minutes", "text"), [(45, "45m"), (60, "1h"), (130, "2h 10m")])
def test_duration_text(minutes: int, text: str) -> None:
    assert duration_text(timedelta(minutes=minutes, seconds=59)) == text


def test_log_lines_read_back_as_the_events_written_from_a_day_on() -> None:
    events = (
        Event(at("09:00"), "started", "Do ticket 1234"),
        Event(at("09:30"), "parked", "Do ticket 1234", "left off: retry loop · trace"),
        Event(at("09:31"), "unfocused", "Glance\u2028overlay"),  # tasks.md allows other breaks
    )
    text = "".join(f"{events_log.line(event)}\n" for event in events)
    narrower = "2026-10-18 09:00:00+01:00  started   Do ticket 1234\n"  # before `unfocused`
    assert events_log.parse(f"{narrower}\n{text}") == History((events[0], *events))
    dotted = events_log.line(Event(at("09:00"), "parked", "a · b ·", "left off: x"))
    older = "2026-10-18 09:00:00+01:00  started   a·b"  # an older glance kept this `·`
    parked = Event(at("09:00"), "parked", "a - b -", "left off: x")
    started = Event(at("09:00"), "started", "a-b")
    assert events_log.parse(f"{dotted}\n{older}") == History((parked, started))


@pytest.mark.parametrize(
    ("line", "message"),
    [
        ("yesterday  started  1135", "a line is a time, what happened, then the task"),
        ("2026-10-18 09:00:00+01:00  napped  1135", "'napped' isn't something glance logs"),
        (
            "2026-10-30 25:00:00+01:00  started  1135",
            "'2026-10-30 25:00:00+01:00' isn't a real time, like 2026-10-17 09:58:40+01:00",
        ),
        (
            "2026-10-30 0\u0669:00:00+01:00  started  1135",  # a digit, but not one 0-9
            "'2026-10-30 0\u0669:00:00+01:00' isn't a real time, like 2026-10-17 09:58:40+01:00",
        ),
    ],
)
def test_a_line_that_does_not_fit_refuses_the_log(line: str, message: str) -> None:
    text = f"2026-10-18 08:00:00+01:00  started  ok\n{line}\n"
    assert events_log.parse(text) == Problem(2, message)
    assert day(Problem(2, message), at("10:00"), at("00:00"), Idle()) == Day(
        at("10:00"), at("00:00"), problem=f"events.log line 2: {message}"
    )
