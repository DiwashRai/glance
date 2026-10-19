# Glance: vision

Glance started as an always-on bar of counts (email, reviews, Jira) so I could stay focused without
forgetting the outside world. The next step: a tool that remembers what I'm doing, keeps me on it,
helps me choose what's next, and brings me back after interruptions. I can talk to it.

Simplify aggressively. If a feature isn't clearly helping one of the problems below, cut it.

## Words used here

| Word | Meaning |
|---|---|
| HUD | The thin bar that is always on screen, on the taskbar by the tray. Shows the counts, and the active task unless I turn it off. |
| Overlay | The bigger panel that opens with Ctrl+Space: a text box in the middle, lists around it. |
| Drop card | A small card that springs out of the HUD to nudge me, with one-key answers. |
| Agent | The AI assistant: Copilot CLI at work, Claude CLI at home. |
| MCP server | The set of tools the agent uses to read and change glance's lists. |
| Provider | Code that fetches data from one service (Jira, GitHub, Outlook, Todoist). |
| Watcher | The background program that checks providers and spots changes. Today's "collector" grows into it. |
| herdr | My terminal tool that keeps agents running in panes. |
| Day snapshot | A short summary of today (time, calendar, lists, stats) that the agent reads. |
| 1135, 1129, ... | Jira ticket numbers, used as examples. |

## The problem

- **Getting back is hard; doing the work isn't.** When I stay on a task I finish it quickly. Builds,
  agents, Teams messages, calls and meetings pull me away, and I don't go back to the task.
- **No clear "next".** After finishing something I often don't know what to pick up.
- **Stuck work goes quiet.** I park things that are uncertain or arduous, and they disappear.
- **Time blindness.** Two hours pass while I think it's been forty minutes.
- **Plans drift.** I run over when I'm in the zone (12:55, run planned for 13:00, I keep going), and
  my estimates are optimistic (a 1h task takes 2h). The rest of the day doesn't adjust.
- **Tools get forgotten.** Anything that relies on me remembering to use it fails once I'm absorbed
  or someone grabs my attention.

## Principles

- **Works when forgotten.** The HUD is always there and needs no effort. The active task can live on it.
- **Assistant, not boss.** The agent gives its opinion and suggests. It never overrules me.
- **Safe to put things away.** Anything parked is guaranteed to come back. Nothing silently
  disappears.
- **Going all in is fine.** If I drop everything for something urgent, the agent just tells me what
  gets parked ("this parks 1135, OK?") and keeps it safe. No quotas or time budgets.
- **Plain code first, AI second.** Clear rules are ordinary code: list limits, check-in timing,
  commands, spotting gaps and overruns. The agent is only used when something needs interpretation
  or judgement, and it works through the same tools.
- **Plain names.** Nothing on screen should need explaining to someone looking over my shoulder.
- **Finishing or switching happens in the overlay.** Glance has no shortcut that finishes or
  switches a task without opening the overlay, so I always see what's next. That builds the habit of
  coming back to it. (If the agent changes something from a terminal, the next overlay shows it.)

## Lists

The priority side is read top to bottom: "can I do this right now? No? Next one."

| List | Limit | What it holds |
|---|---|---|
| Active | 1 | What I'm working on right now. Shown on the HUD unless I turn that off. |
| Focus | 1-2 | What the work is for, kept in view as a reminder: something I need to deliver ("fix the vulnerabilities"), or something I'm chipping away at over time ("migrate the build", in its own worktree). Never made active. Two at most, so I chip away at one or two things instead of carrying five that never get done. Still loose: it may become a queue later. |
| Parked | any | Tasks I've put away: paused or blocked. |

Parked in more detail:

- A paused task has a "where I left off" note. A blocked task says what it's waiting on.
- Only the most recently touched few are shown; the rest are one search away.
- A blocked task is marked "ready" when it's unblocked.
- Parked tasks come back in the morning routine and whenever Active is empty.
- After about a week untouched, glance asks "keep or drop?".

The time side:

| List | What it holds |
|---|---|
| Today | A timeline of meetings, my planned blocks, and what I actually worked on. |
| Quick | Small things to do while I wait for a build or an agent, with an optional rough size (`~3m`): follow-ups ("merge 1129"), admin, small reviews. Smallest first, so I pick by "what fits in the time I have", not by priority. Keeping them quick is the point: anything longer deserves its own block. |

Glance keeps its own files for these lists (see Data). Task titles stay short at work ("do ticket
1135"); the detail lives in Jira, GitHub and so on. Starting a new task parks the active one and
says so.

## Steps

- A task can have steps: an ordered checklist, one level only (no steps inside steps).
- One step is the current step. The Active card shows it with progress (`compare node versions ·
  2/4`); the HUD shows the step and its progress in place of the title, since it has little room. A parked task with no note shows
  its step instead.
- `done` ticks off the current step and moves to the next. After the last step it says "all 4
  steps done · done again to finish", so finishing takes a second `done`.
- `skip` (or `>`) moves past a blocked step and leaves it in the list. Once the open steps run out,
  glance comes back round to the skipped ones. Skipping one again leaves it for good, and when only
  those are left, `done` finishes anyway and says how many were skipped.
- `finish` finishes the task early, whatever its steps.
- A step that turns out to be big becomes its own task.
- Parking keeps my place, so the step itself works as the "left off" note.
- Steps come from typing (`step rerun CI with trace`), from the breakdown helper, or optionally from
  Jira subtasks.
- Check-ins and time estimates work per step ("34m on 'compare node versions', planned 15m").

## Commands and keys

Typed into the overlay's text box. A command word first decides. With none, a line ending in a
time and a length is a block, and anything else is a new task. A line starting with one space goes
to my assistant agent, two or more to my chief of staff (both in herdr, typed into their panes).
As I type, the words glance picked up are coloured, so I can see what it will do.

| Command | Does |
|---|---|
| `park <note>` (also `pause`, `shelve`, `defer`) | Park the active task with a "left off" note |
| `wait <reason>` | Park the active task as blocked on something |
| `switch <name>` (or `s`) | Make a parked task active; the current one is parked |
| `<title>`, or `new <title>` (or `+`) | Start a new task; the current one is parked |
| `done` (or `d`) | Finish the current step, or the task if it has no steps. `done q2` ticks off a Quick item without starting it |
| `skip` (or `>`) | Skip the current step; skipped steps come back round once |
| `finish` | Finish the active task now, whatever its steps |
| `step <text>` | Add a step |
| `quick <text>` (or `q`) | Add a Quick item, with an optional size at the end (`~3m`, `~1h`). Switching to one (`s q2`) and parking it puts it back in Quick; parking it with a note or as waiting makes it a parked task |
| `focus <text>` | Add to Focus, if a slot is free |
| `unfocus <name or number>` | Take something out of Focus |
| `<what> <time> for <length>` | Plan a block today: `deep work 2pm for 2h`, or `call for 30m 9` (the next 9 o'clock). `!` at the end marks it must-happen. It cuts back any block it lands on, except a must-happen one |
| `unblock <name or number>` | Take a block off today's plan |

Keys in the overlay and on drop cards:

| Key | Does |
|---|---|
| Ctrl+Space | Tap: open the overlay to type. Hold (300 ms or more): peek without taking the focus, and it hides on release. |
| ↵ | Run the command. On an empty text box: accept the suggestion shown. |
| Esc | Close or dismiss |
| `b` | Break the selected task into steps |
| `?` | Ask what to do next |
| `o` | Continue the agent conversation in a terminal |
| `w` | Show why the agent suggested something |
| 1-3 | Pick an option on a card |

These are a starting set and will change as I use it.

## Check-ins (against time blindness)

When check-ins happen is settled. How they look is covered under Nudges.

- Check-ins happen at `:25` and `:55` past each hour, just before meetings usually start at `:00` and
  `:30`.
- One only appears if at least 30 minutes have passed since I last did something in glance (set,
  switched or parked a task, or answered a check-in). No poke five minutes after starting.
- So the first check-in comes 30-59 minutes after I start, then every 30 minutes.

| Last action in glance | Times checked | First check-in |
|---|---|---|
| 08:20 | 08:25 (5 min, skip), 08:55 (35 min) | 08:55 |
| 08:25 | 08:55 (30 min) | 08:55 |
| 08:26 | 08:55 (29 min, skip), 09:25 (59 min) | 09:25 |

## Nudges

When glance speaks up, besides check-ins:

- **When I open the overlay.** My attention is already free. At most one nudge, chosen in this order:
  a parked task that's now ready, a gap before the next event with a Quick item that fits, a missed
  check-in, a parked task that's gone stale, the first open of the day.
- **When I come back after being away.** "Back to 1135? Left off: ...". Glance knows I was away
  from the time since my last key press or mouse move (the same signal Teams uses to show "Away"),
  and from screen lock/unlock and cloud PC reconnects. It never reads keystrokes or what I was
  doing. It doesn't take keyboard focus, since I may be coming back to reply to someone.
- **5 minutes before a meeting.** "Standup in 5m, note where you are?"
- **5 minutes before a planned block ends.** "Deep work ends in 5m."
- **When a parked task is unblocked.**
- **When Active becomes empty** by any route (for example, ticked off in Todoist): the next overlay
  opens on "what's next?".

Gaps aren't detected directly. Opening the overlay (or coming back) plus the calendar is enough:
"opened at 14:54, 1:1 at 15:00, so 6 minutes free".

**Quiet first, louder only if needed.** A dot on the HUD comes first. A drop card only appears if I
ignore the dot, or if it's urgent. This applies to every nudge, including changes the watcher finds.

We choose how nudges look by building animated prototypes and comparing them. First round: the drop
card won clearly. It springs out of the HUD and offers one-key answers like resume, switch, break it
down, do it now. Lead with the task, not a greeting: "Back to 1135?", not "Welcome back".

## Planning the day

The agent helps plan the day, and glance keeps the plan honest as the day goes.

- **Two kinds of block.** Fixed: meetings from the calendar; glance never moves them. Flexible: my
  own blocks (deep work, PR reviews, a run), which can move. A flexible block can be marked "must
  happen today" (the run), so it gets moved rather than dropped. Blocks only move when I say so
  (`extend`, or accepting a card); a block I type cuts back the ones it lands on, but never a
  must-happen one.
- **Running over is spotted by plain code.** Five minutes before a block ends, the "ends in 5m"
  nudge appears. If the end time passes and I'm still on the same task, an overrun drop card offers:
  wrap up in 5 minutes, push the next block by 30 minutes, or move it to the next free slot that
  fits (found by plain code from the calendar).
- **Small moves happen by themselves.** My flexible blocks shift later (for example after "keep
  going 30m") with a short "moved" notice and one-key undo. Anything that drops or shortens a block,
  or crosses a meeting, is a suggestion I have to accept.
- **The agent helps when the reshuffle is hard**: pushing would run into a meeting or past the end
  of the day, something has to give, or I ask in my own words. It suggests; I accept with one key.
  It also edits the plan whenever I ask ("fill in my blocks for today").
- **Respect the zone, but don't let health things vanish.** The first overrun card is gentle and
  offers to keep going. If a must-happen block has already been pushed once, the next card says so
  plainly ("run pushed once already, next free hour is 17:30").
- **Estimates learn from what happens.** Glance already records when tasks and steps start, park
  and finish, so it can compare planned and actual time without me logging anything. Plain code
  works out the numbers ("tickets planned at 1h took 1h50 on average, last 10"). The agent uses them
  when planning ("you said 1h; similar tasks take about 2h, plan 2h?"), and writes patterns it
  notices to `notes.md` ("runs slip when they come right after deep work") for me to confirm.

## Two helpers: breaking down and prioritising

Both run inside the overlay, using the agent. I don't need to open a terminal. `o` continues the
same conversation in a terminal when I want to go deeper; changes made there still land in glance.

**Breaking down a ticket** (`b`, "break down 1098", or "break it down" on a drop card):

- The agent gets the ticket's title and description from Jira, my "left off" note and my time
  estimates. If the Jira project is linked to a repo folder, the agent works in that repo so the
  steps can point at real code.
- It returns a short checklist. The first step is always tiny (10 minutes or less, starting with a
  verb), because starting is the hard part. Anything uncertain becomes a short "find out" step with
  a time limit.
- I refine it by typing ("make step 1 smaller"). ↵ saves it as the task's steps (see Steps).

**Prioritising** (Active becomes empty, the morning routine, `?`, or "what should I do next?"):

- Plain code makes a shortlist first: ready tasks, deadlines, Focus, long-parked tasks, things that
  fit the next free slot. That keeps the agent's job small and fast.
- The agent adds judgement from my goals, calendar, time estimates and `notes.md`. It returns one
  recommendation with a reason, plus two alternatives. ↵ makes it active; 1 or 2 picks another; `w`
  shows why.
- Requests like "reorder my parked list" come back as suggestions to accept.

## Watchers

The agent can't watch anything by itself. The watcher does the watching and only wakes the agent
when needed.

- **Look at items, not just counts.** Providers return items with IDs. Each check compares them with
  the previous results to find what changed: "PR #415 now wants my review", "1137 assigned back to
  me", "1129 approved". A count can stay the same while the items behind it change.
- **Watch exactly what I'm waiting on.** Parking a task as waiting on a CI run or a PR starts a
  watch on just that (`gh run watch`, `gh pr checks --watch`, or checking the PR). When it finishes,
  the parked task is marked ready or flagged ("1135's CI failed").
- **Rules handle the obvious changes.** An approved PR marks its parked task ready and adds "merge"
  to Quick. A new review request becomes a Quick item.
- **The agent handles the unclear ones.** For example, a newly assigned ticket: urgent or not? It
  gets the ticket number, the title and the day snapshot, and decides: ignore, add to Quick, link to
  a parked task, mention next time I open the overlay, or interrupt now with a drop card. Interrupting
  follows the "quiet first" rule from Nudges, and is less likely during deep work.
- Changes are batched over a couple of minutes, so the agent is woken once, not per item, with a cap
  on wake-ups per hour.
- The watcher runs all the time in the background. It checks providers, runs the targeted watches,
  and writes the changes to its own file, where the HUD picks them up.

## Layout

The chosen overlay design is board F ("Balanced columns + animated Active") on the design canvas:
https://claude.ai/artifact/74pBpUYyeYhkLdDXNPL8yX. The nudge prototypes are on the same canvas
("Nudge lab" and "On open"). The canvas is private to me.

- The text box is in the middle. The priority lists are stacked cards on the left. The time side
  (Today, Quick) is on the right. Everything sits toward the centre, not the screen edges.
- While I type, the side my command affects lights up and the rest fades.
- Active sits right above the text box: normal-size text, an orange border and a small flame.
- Making a task active or parking it is animated, so I can see it move to Parked. Small enjoyable
  details make me more likely to keep using it.
- **Tactile feel is the secret ingredient.** Tasks should feel like physical objects slotting in and
  out of place. This needs a lot of tuning (timing, easing, bounce, maybe sound) once there's a real
  version, and it's worth the effort.
- Both side columns have the same fixed height. Parked shows as many recent items as fit. Quick
  shows the top few plus "+N more". Today shows 1 hour back and 3 hours ahead, stretched to fill
  the space (any more and a half-hour bar is too thin to label), with later events listed
  underneath.
- Ctrl+Space opens it (taking over from Todoist quick add). The more often I open it, the more
  natural it is for nudges to show up there.

## Environments

| | Work (cloud PC) | Home (personal laptop) |
|---|---|---|
| HUD and overlay | glance, work settings | glance, home settings |
| Agent | Copilot CLI | Claude CLI |
| Tools | glance MCP server | glance MCP server, plus personal mail |
| Sources | Jira, GitHub, Outlook mail, Outlook calendar (Teams meetings), Todoist | Personal mail, Todoist (tasks, chores, reminders, tasks with a time), Teams meetings |

Each environment keeps its own lists; nothing syncs between them. Work content stays on the cloud
PC. The agent's notes about how I work are kept separately in each environment.

## Data

Plain files on each machine, kept out of OneDrive-synced folders:

- `tasks.md`: the lists (Active, Focus, Parked with notes and waiting-on reasons), steps, Quick
  items and today's planned blocks (under `# Today 2026-10-18`; another day's are ignored), as
  plain Markdown that I or an agent can read and edit. Glance rewrites it in a fixed
  form after every command, saves it safely (write a temp file, then swap it in), refuses a file
  it can't read rather than guessing, and notices when it was edited outside glance.
- `events.log`: a running log of what happened (started, parked, finished, check-in answered,
  block moved), one line per event, lined up in columns. Gives "what did I do today" and planned
  vs actual time.
- `notes.md`: the agent's notes on how I work. I can read and edit it.

Todoist is read, never written. Tasks due today, and anything I capture on my phone (the Todoist
inbox), show up in glance for me to sort into lists. Personal reminders stay in Todoist. No glance
lists on my phone.

## AI

- **Plain code does**: commands, list limits, check-ins, nudge timing and which nudge to show,
  spotting gaps and overruns, finding free slots, spotting unblocked tasks, time statistics.
- **The agent does**: requests in my own words, breaking tasks down, suggesting priorities,
  planning the day, hard reshuffles, noticing patterns.
- **What the agent knows**: it reads the day snapshot through one MCP tool: the time, today's
  calendar and blocks, Active and how long I've been on it, Focus, Parked, Quick, time statistics,
  my longer-term goals and `notes.md`.
- **Suggestions, not changes.** When the overlay asks the agent something, the agent's changes are
  recorded as suggestions. The overlay lists them and ↵ applies them. When I talk to the agent in a
  terminal, changes apply directly.
- The agent only runs when I ask, or when plain code hits a case it can't handle. That keeps it
  cheap and predictable. Expect a few seconds per answer; commands stay instant.
- **How glance reaches the agent is a setting**: either run the CLI once per request, or send the
  request to my always-on assistant agent in herdr, which remembers the day's context. Details are
  in the appendix.

## Main parts

- **glance app** (Python, PySide6): the HUD, the overlay, Ctrl+Space, commands, check-in and overrun
  timers, drop cards.
- **Watcher** (Python): runs in the background, checks providers, finds changes, wakes the agent
  when needed.
- **MCP server** (Python, later): changes the lists through the same rules as the app. Tools for
  the lists, steps, Quick items, today's blocks, the day snapshot, breaking down a task into steps,
  reading provider data, and reading and adding to `notes.md`. Used by Copilot CLI at work and
  Claude CLI at home.
- **Agent connector**: sends a request to the agent the way the settings say (see appendix).
- Tooling: ruff, pyright (strict), pytest.

## Out of scope

- Manual time logging (Toggl, Timery). Times come from the event log and are only used for
  planning.
- Watching Teams or calls.
- A weekly budget for "fun" or improvement work.
- Two-way Todoist sync, or glance lists on my phone.
- Sending detailed work content to a personal AI or to Todoist.

## Open questions

- Should check-ins pause while the PC is locked or I'm away?

## Appendix: how glance reaches the agent

**Built so far:** only herdr, and only as if I'd typed into the agent's pane
(`herdr agent prompt <name> "<text>"`): one space for `assistant`, two for `chief`. There's no
fallback, request ID or reply in glance yet; the answer stays in the agent's pane. The plan below
is where it may go.

Two ways, chosen in settings, behind one small interface (like providers today):

- `headless`: run the CLI once per request (`copilot -p ...` or `claude -p ...`; the command is a
  template in settings). No window.
- `herdr`: send the request to a long-running "assistant" agent in a herdr pane
  (`herdr agent prompt <target> "<text>" --wait`). It keeps the day's context between requests.
  `o` becomes `herdr agent focus <target>`, which jumps straight into the same conversation.

Rules that apply to both:

- The answer always comes back through the MCP tools (suggestions plus a short reply), never by
  reading the agent's terminal output.
- Glance sends one short line with a request ID. The agent fetches the context itself with the day
  snapshot tool.
- If the herdr assistant is busy (I'm mid-conversation with it) or not running, glance falls back
  to `headless` instead of interrupting the conversation.
- Different purposes can go different ways. For example, the watcher's questions go `headless` so
  they don't clutter my conversation with the assistant.
- Starting the assistant fresh each morning (from `notes.md` and the day snapshot) keeps its
  conversation from growing all day.

```toml
[agent]
backend = "herdr"        # or "headless"
fallback = "headless"    # when the herdr agent is busy or not running

[agent.headless]
command = ["copilot", "-p", "{prompt}"]

[agent.herdr]
target = "assistant"
timeout_ms = 120000

[agent.routes]
triage = "headless"      # the watcher's questions
```
