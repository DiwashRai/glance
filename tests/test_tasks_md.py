import pytest

from app.core.model import FromQuick, Idle, LeftOff, Lists, ParkedTask, Task, Waiting
from app.core.tasks_md import Problem, parse, render

EXAMPLE = """\
# Active
- Do ticket 1234

# Focus
- Fix the vulnerabilities
- Migrate the build to uv

# Parked
- 1129 password reset flow
  waiting on: review
- Tidy logging config
  left off: half done on chore/logging
- 1087 onboarding docs ~2h

# Quick
- merge 1129 ~3m
- review #415 ~90m
- reply to Sam
"""

LISTS = Lists(
    Task("Do ticket 1234"),
    (
        ParkedTask(Task("1129 password reset flow"), Waiting("review")),
        ParkedTask(Task("Tidy logging config"), LeftOff("half done on chore/logging")),
        ParkedTask(Task("1087 onboarding docs", 120), LeftOff()),
    ),
    ("Fix the vulnerabilities", "Migrate the build to uv"),
    (
        Task("merge 1129", 3),
        Task("review #415", 90),
        Task("reply to Sam"),
    ),
)
ODD = f"a{chr(0x2028)}b{chr(0x0C)}c"  # characters str.splitlines() would split on


@pytest.mark.parametrize(
    ("text", "lists"),
    [
        (EXAMPLE, LISTS),
        ("# Active\n\n# Focus\n\n# Parked\n\n# Quick\n", Lists()),
        (f"# Active\n- {ODD}\n\n# Focus\n\n# Parked\n\n# Quick\n", Lists(Task(ODD), ())),
        (
            "# Active\n- reply ~5m\n  home: quick\n\n# Focus\n\n# Parked\n\n# Quick\n",
            Lists(FromQuick(Task("reply", 5))),
        ),
    ],
)
def test_round_trips_exactly(text: str, lists: Lists) -> None:
    assert parse(text) == lists
    assert render(lists) == text


@pytest.mark.parametrize(
    ("text", "lists"),
    [
        (
            "# Parked\r\n\r\n- Same\r\n- Same  \r\n\r\n# Active\r\n",
            Lists(
                Idle(), (ParkedTask(Task("Same"), LeftOff()), ParkedTask(Task("Same"), LeftOff()))
            ),
        ),
        (
            "# Parked\n- a\n  Waiting On: CI\n",
            Lists(Idle(), (ParkedTask(Task("a"), Waiting("CI")),)),
        ),
        ("# Parked\n- a\n  left off:\n", Lists(Idle(), (ParkedTask(Task("a"), LeftOff()),))),
    ],
)
def test_reads_hand_edits_leniently(text: str, lists: Lists) -> None:
    assert parse(text) == lists


@pytest.mark.parametrize(
    ("text", "line", "message"),
    [
        ("hello\n# Active\n", 1, "text before the first heading"),
        ("# Active\n# Later\n", 2, "unknown heading '# Later'"),
        ("# Active\n# Active\n", 2, "'# Active' appears twice"),
        ("# Active\n- a\n- b\n", 3, "only one task can be active"),
        ("# Active\n- a\n  left off: x\n", 3, "the active task can only have 'home: quick'"),
        ("# Quick\n- a\n  left off: x\n", 3, "a quick item can't have a note"),
        ("# Quick\n- ~5m\n", 2, "a task needs a title"),
        ("# Parked\n  left off: x\n", 2, "a note goes on its own line under a parked task"),
        ("# Parked\n- a\n  something else\n", 3, "a note starts with 'waiting on:'"),
        ("# Parked\n- a\n  waiting on:\n", 3, "waiting on what?"),
        ("# Parked\n- a\n  - [ ] step\n", 3, "steps aren't supported yet"),
        ("# Parked\n-   \n", 2, "a task needs a title"),
        ("# Parked\n* a\n", 2, "glance can't read this line"),
        ("# Focus\n- a\n- b\n- c\n", 4, "focus holds at most 2"),
        ("# Focus\n- a\n  left off: x\n", 3, "a focus can't have a note"),
    ],
)
def test_refuses_what_it_cant_read_with_the_line(text: str, line: int, message: str) -> None:
    match parse(text):
        case Problem() as problem:
            assert problem.line == line
            assert problem.message.startswith(message)
        case Lists() as lists:
            pytest.fail(f"expected a problem, got {lists}")
