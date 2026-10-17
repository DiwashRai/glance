
# Glance

## summary

A quick and dirty way to have a select few important notifications always visible e.g. emails,
code reviews, jira. This is so that you can remain deeply focused on the current task, whilst being
able to *glance* at what else might be waiting on you without having to context switch to email
clients, browsers etc.

Instructions are for windows at the moment.

## Glance v2 (in progress)

v2 is a task overlay: press Ctrl+Space anywhere to open it, type a command, Enter to run it, Esc
to hide it. It lives in the tray; right-click the orange dot to quit. `docs/vision.md` says where
it's going.

| Command | Does |
|---|---|
| `new <title>` (or `+`) | Start a task. Anything active is parked. |
| `park <note>` (or `pause`, `shelve`, `defer`) | Park the active task, with an optional "left off" note |
| `wait <what>` | Park the active task as waiting on something |
| `switch <title or number>` (or `s`) | Make a parked task active |
| `done` (or `d`) | Finish the active task |

Your lists live in `%LOCALAPPDATA%\glance\tasks.md`, plain Markdown you can edit by hand, and
what happened is logged to `events.log` next to it. Settings go under `[glance]` in
`config.local.toml` (see `config.toml` for the defaults).

v2 takes over the `[glance]` table from the v1 bar, so the v1 bar no longer runs with this
config. If your `config.local.toml` still has v1's keys there (`path`, `poll`, `pos` and so on),
glance stops with "unknown field": back the file up, then delete those keys. Keep `[updater]`,
`[providers]` and `[[entries]]`: they're where the counts come from.

To start it at login, add a Task Scheduler task that runs `scripts\run_glance_v2.cmd` on logon,
with "Run only when user is logged on" (as below for v1). The script needs
[uv](https://docs.astral.sh/uv/): it installs or updates glance's dependencies before starting
it. glance refuses to run a second copy, so starting it twice is harmless.

## Usage (v1)
The repo is set up so you can keep tracked defaults in `config.toml` and personal settings in
`config.local.toml`. The local file is ignored, so your tokens, folder selections, and status
file path do not block `git pull`.

The quickest way to get started is:

```bat
scripts\run_glance.cmd
```

On first run that script will:
- copy `config.toml` to `config.local.toml` if needed
- copy `data\status.json` to `data\status.local.json` if needed
- start the renderer using `config.local.toml`

To refresh counts with the same local config:

```bat
scripts\update_status.cmd
```

If you prefer to run the Python entry points directly, they now look for `config.local.toml`
first and fall back to `config.toml`.

```bat
pythonw.exe "C:\path\to\glance.py" --config "C:\path\to\config.local.toml"
python.exe "C:\path\to\update_status.py" --config "C:\path\to\config.local.toml"
```
Use python.exe and not pythonw.exe if you are making sure that it's starting up and running fine
otherwise you have to kill the process from task manager or using taskkill.

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

### With Task Scheduler:
- Create a task that triggers on logon. Add a delay if you want.
- General: Set 'Run only when user is logged on'
- Action should be: Start a program `C:\Path\to\glance\scripts\run_glance.cmd`
- Settings: If the task is already running the the following rule applies:
  - 'Do not start a new instance'

## Design
- Always on top visibility without being obtrusive
- Read from some sort of status.json that a different background scrip/task will generate
  - simple format that has name, symbol, count/value and severity
  - fast to parse for potential use in a powershell prompt
