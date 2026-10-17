# Working on glance

`docs/vision.md` says what we're building and why. Read it before starting a feature.

## Before you say you're done

Run `just check`, `just gates` and `just test`; all must pass. Put the `just card` output in your
report.

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
  Core is held at 0. Fix it by modelling the data so the check isn't needed (see Code shape). Don't
  move code to another layer to dodge the count.
- **baseline**: a number in `quality-baseline.json` went up without an entry in `raises`. Only
  raise a number if the owner agrees, and record why:
  `{"date": "2026-10-17", "what": "allowed.core.try", "reason": "..."}`.
- **size budget**: a warning only. When a stage goes over its budget, do a simplification pass
  before starting the next stage.

Legacy functions listed in the baseline may stay over a limit, but only at or below their recorded
score. When your change brings a number down, run `just ratchet` and commit the lower baseline with
it.

## Code shape

- **Layers.** `app/core` is pure logic: no I/O, UI, processes, network or clock (import-linter and
  ruff enforce this). The rest of `app/` is the boundary (providers, store, MCP, agents, config,
  Windows calls), which does the I/O and parsing. `glance.py` and `update_status.py` are entry
  points: the only place for a broad `except` or `print`.
- **Absence is a state, not `None`.** Use an empty string or tuple. Use a separate type when absence
  means something: a waiting task always has `waiting_on: str`, an active task has no such field.
- **Parse at the boundary.** Turn untrusted data (config, provider output, data files, MCP input,
  agent suggestions) into frozen types once, and reject it whole if it's wrong. Code past the
  boundary trusts its types and doesn't re-check them.
- **Errors.** A provider catches its own failure and returns a result that says so. Everything else
  propagates to the entry point's handler. No `try`/`except`/`pass`.
- **Small functions.** At most 5 arguments and 40 statements (ruff), plus the complexity gates.
- **Tests.** Pass the clock in; never sleep or read the real time in tests.
