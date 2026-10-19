from datetime import date, time

from app.core.listing import listing
from app.core.model import (
    Block,
    FromQuick,
    LeftOff,
    Lists,
    ParkedTask,
    Plan,
    Step,
    Task,
    Waiting,
)

TODAY = date(2026, 10, 19)
STANDUP = Block(time(9), time(9, 30), "standup")


def test_each_list_is_numbered_the_way_commands_count_it() -> None:
    lists = Lists(
        active=Task("fix the build", steps=(Step("rerun CI", "done"), Step("trace", "skipped"))),
        parked=(
            ParkedTask(Task("review 1129"), Waiting("Sam")),
            ParkedTask(Task("tidy logs", 30), LeftOff("half done")),
            ParkedTask(Task("bump deps", steps=(Step("pin"), Step("test"))), LeftOff()),
            ParkedTask(Task("old idea"), LeftOff()),
        ),
        focus=("fix the vulnerabilities", "ship 2.0"),
        quick=(Task("merge 1129", 3), Task("reply to Sam")),
        plan=Plan(TODAY, (STANDUP, Block(time(18), time(19), "run", must=True))),
    )
    assert listing(lists, TODAY) == (
        "Active\n"
        "  fix the build\n"
        "    [x] rerun CI\n"
        "    [>] trace\n"
        "Focus\n"
        "  1  fix the vulnerabilities\n"
        "  2  ship 2.0\n"
        "Parked\n"
        "  1  review 1129 · waiting on Sam\n"
        "  2  tidy logs ~30m · left off: half done\n"
        "  3  bump deps · pin · 1/2\n"
        "  4  old idea\n"
        "Quick\n"
        "  q1  merge 1129 ~3m\n"
        "  q2  reply to Sam\n"
        "Today\n"
        "  1  09:00-09:30 standup\n"
        "  2  18:00-19:00 run !"
    )


def test_an_empty_list_says_so_and_another_days_plan_is_left_out() -> None:
    yesterday = Plan(date(2026, 10, 18), (STANDUP,))
    lists = Lists(FromQuick(Task("merge 1129", 3)), plan=yesterday)
    assert listing(lists, TODAY) == (
        "Active\n  merge 1129 ~3m · from quick\n"
        "Focus\n  nothing\nParked\n  nothing\nQuick\n  nothing\nToday\n  nothing"
    )
