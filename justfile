# Glance task runner. Run `just` to list the recipes.

set windows-shell := ["pwsh", "-NoLogo", "-NoProfile", "-Command"]

export PYTHONUTF8 := "1"

run := "uv run --extra dev"

# List the recipes
default:
    @just --list

# Lint, format, types, import rules
check:
    {{ run }} ruff check .
    {{ run }} ruff format --check .
    {{ run }} pyright
    {{ run }} lint-imports

# Gates: complexity, fan-out, module size, defensive counts, baseline, size budget
gates:
    {{ run }} python scripts/fitness.py

# Lower the gate baseline where the code improved (it never raises it)
ratchet:
    {{ run }} python scripts/fitness.py --ratchet

# What a change did to the gate numbers, compared with BASE
card base="main":
    {{ run }} python scripts/card.py {{ base }}

# Tests
test:
    {{ run }} pytest

# Auto-fix lint issues and format the code
fix:
    {{ run }} ruff check . --fix
    {{ run }} ruff format .
