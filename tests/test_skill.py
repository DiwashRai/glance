from datetime import datetime, time, timedelta, timezone

import pytest

from app.core.commands import Applied, Ask, apply, parse_command
from app.core.model import (
    Block,
    CommandWords,
    LeftOff,
    Lists,
    ParkedTask,
    Plan,
    Step,
    Task,
    Waiting,
)
from app.core.skill import EXAMPLES, skill

NOW = datetime(2026, 10, 19, 9, 58, 40, tzinfo=timezone(timedelta(hours=1)))
BUSY = Lists(
    active=Task("fix the build", steps=(Step("rerun CI", "done"), Step("read the trace"))),
    parked=(
        ParkedTask(Task("review 1129", starred=True), Waiting("Sam")),
        ParkedTask(Task("write the docs", 30), LeftOff("half done")),
    ),
    focus=("fix the vulnerabilities",),
    quick=(Task("merge 1129", 3), Task("reply to Sam")),
    plan=Plan(NOW.date(), (Block(time(9), time(9, 30), "standup"),)),
)
# What each example in --skill says it does, on BUSY: a new example needs a line here
SAID = {
    "new reply to Sam's email": "added reply to Sam's email to the queue as 3",
    "deep work 2pm for 2h": "planned deep work 14:00-16:00",
    "run 6pm for 1h !": "planned run 18:00-19:00 · must happen today",
    "park stuck on the flaky test": "parked fix the build",
    "wait code review": "waiting on code review",
    "switch 2": "switched to write the docs",
    "step rerun CI": "added step 3",
    "done": "done: read the trace",
    "skip": "skipped: read the trace",
    "finish": "finished fix the build",
    "quick merge 1129 ~3m": "added merge 1129 ~3m to quick",
    "done q1": "finished merge 1129",
    "focus ship the release": "focusing on ship the release",
    "unfocus 1": "unfocused fix the vulnerabilities",
    "unblock 1": "unblocked standup",
    "rm 2": "removed write the docs ~30m from the queue",
    "new ship the release *": "added ship the release to the queue as 1, starred",
    "star 2": "starred write the docs ~30m",
    "unstar 1": "unstarred review 1129",
}


@pytest.mark.parametrize(("line", "does"), EXAMPLES)
def test_every_example_in_the_skill_does_what_it_says(line: str, does: str) -> None:
    command = parse_command(line, CommandWords())
    assert not isinstance(command, Ask)
    result = apply(BUSY, command, NOW)
    assert isinstance(result, Applied), does
    assert SAID[line] in result.message
    quoted = line.replace("'", "''")  # as PowerShell takes it
    assert f"glance '{quoted}'" in skill(CommandWords())


def test_the_skill_is_in_the_owners_command_words() -> None:
    """A default word that's been taken out would start a task instead."""
    shown = skill(CommandWords(done=("complete",), new=("n", "new")))
    assert "glance 'complete q1'" in shown
    assert "glance 'complete' " in shown
    assert "glance 'done" not in shown
    assert "glance 'new reply to Sam''s email'" in shown  # still one of the words: kept
