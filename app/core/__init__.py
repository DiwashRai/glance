"""Glance's pure core: no I/O, UI, processes, network or clock (functions take `now`). Other
layers call into core, never the reverse. AGENTS.md has the rules; `just check` and `just gates`
enforce them.
"""
