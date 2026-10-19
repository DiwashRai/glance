"""What `glance --skill` prints: how an agent uses glance on the command line. Pure: command
words in, text out.
"""

from __future__ import annotations

from app.core.model import CommandWords

# What each kind of line looks like, in the default command words. A test runs each one, so
# they stay right.
EXAMPLES = (
    ("new reply to Sam's email", "start a task, always with this word: the active one is parked"),
    ("deep work 2pm for 2h", "plan a block today: its name, then a time and a length"),
    ("run 6pm for 1h !", "the ! means it must happen: a newer block never cuts it"),
    ("park stuck on the flaky test", "park the active task, with an optional note"),
    ("wait code review", "park it, waiting on something"),
    ("switch docs", "resume a Parked or Quick task by a word in its title, or q1"),
    ("step rerun CI", "add a step to the active task"),
    ("done", "tick the current step; with none open, finish the task"),
    ("skip", "skip the current step"),
    ("finish", "finish the active task, steps or not"),
    ("quick merge 1129 ~3m", "add to Quick; the size is optional"),
    ("done q1", "tick off Quick q1 without starting it"),
    ("focus ship the release", "add a Focus goal (two at most)"),
    ("unfocus 1", "take Focus 1 off"),
    ("unblock 1", "take today's block 1 off"),
    ("rm p2", "take a row off Focus, Parked or Quick: f1, p1 or q1"),
)
SKILL = """\
glance: the owner's working memory

glance holds what the owner is on now and next: one Active task, one or two Focus goals, Parked
tasks, Quick small things and today's time blocks. Keep it small: everything else lives elsewhere.

  glance               show the lists, numbered the way commands count them
  glance '<line>'      run a line, exactly as if the owner typed it into glance
  glance --skill       this

A line goes through the same checks as the owner's own and is saved and logged the same way. One
that works prints what it did; one that's refused prints why, changes nothing and exits 1. Never
edit tasks.md by hand.

{examples}

- One glance command at a time, never in parallel: two at once can lose a change.
- Single quotes, with any ' inside doubled: in double quotes PowerShell changes $ and `.
- A line with no command word plans a block if it ends in a time and a length, and otherwise
  starts a task, parking the owner's. So start tasks as above, and check the reply says what
  you meant.
- Numbers move as the lists change: run `glance` just before using one. In switch, a number
  matches a word in a title (1129) before a Parked row, so switch by a word from the title.
- Times: 2pm, 2:30pm, 14:00, noon, evening. A bare 9 is 9am, or 9pm once 9am has gone. Lengths:
  30m, 1h, 1h30m. Blocks are for today only, and a newer one cuts back any it lands on.
- Steps in the lists: [x] done, [ ] open, [>] skipped, [-] skipped twice.
- Removing, finishing and ticking off can't be undone: do them when the owner asks.
- If glance says a tasks.md line is wrong, tell the owner: don't fix the file.
"""


def skill(words: CommandWords) -> str:
    """The examples in the owner's command words, which config.toml can change: a default word
    that's gone would start a task instead. Quoted for PowerShell."""
    renamed = {
        default[0]: default[0] if default[0] in mine else mine[0]
        for default, mine in zip(vars(CommandWords()).values(), vars(words).values(), strict=True)
    }
    quoted = [(f"'{_renamed(line, renamed).replace("'", "''")}'", does) for line, does in EXAMPLES]
    width = max(len(line) for line, _ in quoted)
    examples = (f"  glance {line:<{width}}  {does}" for line, does in quoted)
    return SKILL.format(examples="\n".join(examples))


def _renamed(line: str, renamed: dict[str, str]) -> str:
    first, space, rest = line.partition(" ")
    return f"{renamed.get(first, first)}{space}{rest}"
