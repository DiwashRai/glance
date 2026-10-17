"""Glance's pure core: list rules, steps, scheduling, check-in timing.

Rules for this package (enforced by `just check` and `just gates`):

- No I/O, UI, subprocesses, network or OS access. Other layers call into core, never the reverse.
- No reading the clock. Functions take "now" as a parameter.
- No `try`, `isinstance`, `is None` or `X | None` in signatures. Model absence as its own state
  (an empty string, an empty tuple, a separate type) and parse untrusted data at the boundary.
"""
