
# Glance

## summary

A way to stay deeply focused on one task while still being able to *glance* at what else is
waiting on you (emails, code reviews, Jira), without context switching to email clients,
browsers and so on. `docs/vision.md` says where it's going.

Instructions are for Windows at the moment.

## Using it

Glance has two parts:

- **The HUD:** one row on the taskbar, just left of the tray. The active task, then each count
  (unread mail, reviews, tickets), coloured by how urgent it is. A green ✓ when all is clear.
  Click it to open the overlay.
- **The overlay:** press Ctrl+Space anywhere to open it, type a command, Enter to run it, Esc to
  hide it. Glance lives in the tray; right-click the orange dot to quit.

| Command | Does |
|---|---|
| `new <title>` (or `+`) | Start a task. Anything active is parked. |
| `park <note>` (or `pause`, `shelve`, `defer`) | Park the active task, with an optional "left off" note |
| `wait <what>` | Park the active task as waiting on something |
| `switch <title or number>` (or `s`) | Make a parked task active, or a Quick item (`s q2`) |
| `done` (or `d`) | Tick off the current step, or finish the task if it has none. `done q2` ticks off a Quick item |
| `step <text>` | Add a step to the active task |
| `skip` (or `>`) | Skip the current step; skipped steps come back round once |
| `finish` | Finish the active task now, whatever its steps |
| `focus <text>` | Keep one of at most two goals in view, above Parked |
| `unfocus <name or number>` | Take a goal out of Focus |
| `quick <text> ~5m` (or `q`) | Add something small to do while you wait; the size is optional |

Your lists live in `%LOCALAPPDATA%\glance\tasks.md`, plain Markdown you can edit by hand, and
what happened is logged to `events.log` next to it.

## Setting it up

You need [uv](https://docs.astral.sh/uv/). Then:

```bat
scripts\run_glance.cmd
```

It installs or updates glance's dependencies, collects the counts once, and starts glance.
glance refuses to run a second copy, so starting it twice is harmless.

**Settings.** Keep tracked defaults in `config.toml` and your own settings in
`config.local.toml`, which git ignores, so your tokens don't block `git pull`. Glance and the
collector use `config.local.toml` if it exists, else `config.toml`.

- `[glance]`: glance's own settings, all optional (see `config.toml`).
- `[updater]`, `[providers]` and `[[entries]]`: where the counts come from. Each entry's `icon`
  can be `mail`, `todo`, `jira` or `pr` for an outline icon, or any text, such as a Nerd Font
  glyph.

**The counts.** `update_status.py` (the collector) asks each provider for its count and writes
them to `[updater].output_path`, which the HUD reads. It runs once and exits, so schedule
`scripts\update_status.vbs` (it runs `update_status.cmd` with no window) to keep the counts
fresh. Run `scripts\update_status.cmd --dry-run` to see what it would write.

**Start at login,** with Task Scheduler:
- Create a task that triggers on logon. Add a delay if you want.
- General: set "Run only when user is logged on".
- Action: start a program, `C:\Path\to\glance\scripts\run_glance.cmd`.
- Settings: if the task is already running, "Do not start a new instance".

## Development

You need [uv](https://docs.astral.sh/uv/) and [just](https://just.systems/). Then:

```bat
just check   :: lint, format check, types, import rules
just gates   :: complexity, fan-out, module size, defensive counts (quality-baseline.json)
just card    :: what your change did to the gate numbers
just test    :: tests
just fix     :: auto-fix lint issues and format
```

`AGENTS.md` explains the gates and the code style they enforce.
