# Working on glance

`docs/vision.md` says what we're building and why. Read it before starting a feature.

## Before you say you're done

Run `just check`, `just gates` and `just test`; all must pass. Put the `just card glance-v2`
output in your report (v2 work branches off `glance-v2`).

| Command | What it does |
|---|---|
| `just check` | ruff lint and format check, pyright strict, import rules |
| `just gates` | The gates (below) |
| `just test` | pytest |
| `just fix` | Auto-fix lint issues and format |
| `just card` | What your change did to the gate numbers, compared with `main` |
| `just ratchet` | Lower the baseline after the code improved |

## Gates

Measured limits on the whole codebase. The numbers live in `quality-baseline.json`. When one fails:

- **cognitive**: a function's cognitive complexity is over 15 (complexipy). Split it up: smaller
  helpers, early returns, lookup tables.
- **cyclomatic**: a function's cyclomatic complexity is over 10 (ruff C901). Same fix.
- **fan-out**: a module imports more than 5 glance modules. Pass things in instead of reaching for
  them.
- **module size**: a module has more than 1000 code lines. Split it.
- **defensive**: each layer's count of `is None` checks, `X | None` in signatures, `isinstance`
  calls, `try` blocks, broad `except`s and suppressions (`noqa`, `pyright: ignore`) can't go up.
  A `match` pattern on a built-in type (`case str(x)`, `case int()`) counts as an `isinstance`.
  Core is held at 0. Fix it by modelling the data so the check isn't needed (see Code shape). Don't
  move code to another layer, or reword a check, to dodge the count.
- **baseline**: a number in `quality-baseline.json` went up without an entry in `raises`. Only
  raise a number if the owner agrees, and record why:
  `{"date": "2026-10-17", "what": "allowed.core.try", "reason": "..."}`.
- **size budget**: a warning only. When a stage goes over its budget, do a simplification pass
  before starting the next stage.

Legacy functions listed in the baseline may stay over a limit, but only at or below their recorded
score. When your change brings a number down, run `just ratchet` and commit the lower baseline with
it.

## Code shape

**The core idea: check at the edges, trust the types inside.** Anything from outside glance (data
files, config, provider output, Windows calls, what the user types, agent suggestions) is checked
once, where it comes in, and turned straight into our own frozen types. Anything that doesn't fit
is rejected whole, with a clear reason. Past that point, code trusts its types and lets pyright
catch mistakes: no re-checking, no `isinstance` or `is None` just in case, no defensive `try`.

- **Let a library do the checking at the edges.** Untyped data (TOML, JSON) becomes our types
  with one `msgspec.convert` or `msgspec.json.decode` call, not a chain of hand-written checks.
- **Make bad states impossible to write down.** Absence is a state, not `None`: use an empty string
  or tuple, or a type of its own (`Idle`). A parked task is `LeftOff` or `Waiting`, never both or
  neither. Use tuples, not lists, in frozen types.
- **Expected outcomes are values.** A rejected command or a file that can't be read is returned
  (`Rejected`, `Problem`) and handled with `match`, which is for our own closed types.
- **Layers.** `app/core` is pure logic: no I/O, UI, processes, network or clock (import-linter and
  ruff enforce this). Pure text parsing, such as turning `tasks.md` into lists, belongs in core.
  The rest of `app/` is the boundary (providers, store, config, Windows calls), which does the
  I/O. `glance.py` and `update_status.py` are entry points: the only place for a
  broad `except` or `print`.
- **Errors.** A provider catches its own failure and returns a result that says so. In the new
  app, everything else goes to the one error hook (`sys.excepthook`) that the app installs at
  start-up: during start-up it shows the error and exits, after that it logs, shows the error and
  keeps running. No other code catches. No `try`/`except`/`pass`.
- **Small functions.** At most 5 arguments and 40 statements (ruff), plus the complexity gates.
- **Tests.** Pass the clock in; never sleep or read the real time in tests.
